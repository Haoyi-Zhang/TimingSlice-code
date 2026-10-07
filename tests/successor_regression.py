"""Explicit portable finite regression, not part of historical test receipts.

SPDX-License-Identifier: MIT
Reference enumerates complete prefixes without state/history merging; no private
paths, historical implementation, clocks, compiler or external systems.
"""
import copy
import itertools
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src import checker,producer


def literal(expr,env,widths):
    op=expr[0]
    if op=='const': return expr[2],expr[1]
    if op=='var': return env[expr[1]],widths[expr[1]]
    if op=='slice':
        a,_=literal(expr[1],env,widths); return (a>>expr[2])%2**expr[3],expr[3]
    xs=[literal(e,env,widths) for e in expr[1:]]; a,w=xs[0]
    if op=='not': return (2**w-1)^a,w
    b,bw=xs[1]
    if op=='mux': return xs[1] if a else xs[2]
    if op=='eq': return int(a==b),1
    if op=='ult': return int(a<b),1
    if op=='concat': return a*2**bw+b,w+bw
    value={'and':lambda:a&b,'or':lambda:a|b,'xor':lambda:a^b,
           'add':lambda:a+b,'sub':lambda:a-b}[op]()
    return value%2**w,w


def step(raw,state,u,cut):
    widths={d['name']:d['width'] for key in ('inputs','registers','wires') for d in raw[key]}
    env=dict(zip([d['name'] for d in raw['registers']],state))
    env.update(zip([d['name'] for d in raw['inputs']],u))
    for d in raw['wires']:
        env[d['name']]=cut['w:'+d['name']] if 'w:'+d['name'] in cut else literal(d['expr'],env,widths)[0]
    done=literal(raw['done'],env,widths)[0]
    next_state=tuple(cut['r:'+d['name']] if 'r:'+d['name'] in cut else literal(d['next'],env,widths)[0] for d in raw['registers'])
    return done,next_state


def free(raw,keep):
    return [[(p+d['name'],d['width']) for d in raw[key] if d['cut'] and p+d['name'] not in keep]
            for key,p in [('wires','w:'),('registers','r:')]]


def prefixes(raw,keep,mode,d):
    """Enumerate whole input prefixes first, then whole shared-definition cuts."""
    wc,rc=free(raw,keep); alphabet=list(itertools.product(*(a['values'] for a in raw['inputs'])))
    fields=[wc+(rc if t<d else []) for t in range(d+1)]
    cuts=[list(itertools.product(*(range(2**w) for _,w in f))) for f in fields]
    for us in itertools.product(alphabet,repeat=d+1):
        for cs in itertools.product(*cuts):
            s=a=tuple(r['init'] for r in raw['registers'])
            assignments=[dict(zip([k for k,_ in f],vals)) for f,vals in zip(fields,cs)]
            for t in range(d+1):
                ds,ns=step(raw,s,us[t],{}); da,na=step(raw,a,us[t],assignments[t])
                if t==d:
                    yield (s,a),us,cs,assignments,ds,da; break
                if ds!=da or (mode=='first-hit' and ds): break
                s,a=ns,na


def reference(raw,keep,mode):
    layers=[]
    for d in range(raw['horizon']+1):
        rows=set()
        for pair,us,cs,assignments,ds,da in prefixes(raw,keep,mode,d):
            rows.add(pair)
            if ds!=da:
                return 'invalid',dict(kind='counterexample',retained=sorted(keep),horizon=raw['horizon'],
                    observation=mode,time=d,inputs=[list(u) for u in us],cuts=assignments)
        layers.append([[list(s),list(a)] for s,a in sorted(rows)])
    return 'valid',dict(kind='preservation',retained=sorted(keep),horizon=raw['horizon'],observation=mode,frontiers=layers)


def sign(a,b): return int(a>b)-int(a<b)


def exclusion(raw,witness):
    wc,rc=free(raw,set(witness['retained'])); layers=[]
    target_u=tuple(tuple(u) for u in witness['inputs'])
    target_c=tuple(tuple(witness['cuts'][t][k] for k,_ in wc+(rc if t<witness['time'] else [])) for t in range(witness['time']+1))
    for d in range(witness['time']+1):
        rows={(s,a,sign(us[:d],target_u[:d]),sign(cs[:d],target_c[:d]))
              for (s,a),us,cs,_,_,_ in prefixes(raw,set(witness['retained']),witness['observation'],d)}
        layers.append([[list(s),list(a),i,j] for s,a,i,j in sorted(rows)])
    return dict(frontiers=layers)


def expected_work(raw,cert):
    is_negative=cert['kind']=='counterexample'; depth=cert['time'] if is_negative else raw['horizon']
    layers=cert['predecessors']['frontiers'] if is_negative else cert['frontiers']
    observations=depth+1 if is_negative else 0; successors=depth if is_negative else 0
    wc,rc=free(raw,set(cert['retained'])); progressing=depth if is_negative else 0
    alphabet=list(itertools.product(*(d['values'] for d in raw['inputs'])))
    for t,layer in enumerate(layers):
        for row in layer:
            for u in alphabet:
                ds,_=step(raw,tuple(row[0]),u,{})
                observations+=2**sum(w for _,w in wc)
                if t<depth and not (cert['observation']=='first-hit' and ds):
                    successors+=2**sum(w for _,w in wc+rc); progressing+=1
    return observations,successors,progressing


def tiny_models():
    for width,initial,horizon,observed in itertools.product((1,2),(0,1),(0,1,2),('never','initial','counter')):
        done=['const',1,0] if observed=='never' else (['const',1,1] if observed=='initial' else ['eq',['var','q'],['const',width,1]])
        yield dict(id=f'owned-{width}-{initial}-{horizon}-{observed}',inputs=[dict(name='u',width=1,values=[0,1])],
            registers=[dict(name='q',width=width,init=initial,next=['add',['var','q'],['const',width,1]],cut=True)],
            wires=[dict(name='x',width=1,expr=['var','u'],cut=True)],
            done=['xor',done,['xor',['var','x'],['var','x']]],horizon=horizon)
    for horizon,done in itertools.product((0,1,2),(0,1)):
        yield dict(id=f'empty-{horizon}-{done}',inputs=[],registers=[],
            wires=[dict(name='x',width=1,expr=['const',1,1],cut=True)],
            done=['xor',['const',1,done],['xor',['var','x'],['var','x']]],horizon=horizon)
    yield dict(id='old-state',inputs=[],registers=[
        dict(name='a',width=1,init=0,next=['not',['var','a']],cut=True),
        dict(name='b',width=1,init=0,next=['var','a'],cut=True)],wires=[],done=['var','b'],horizon=2)


def tiny_queries():
    for raw in tiny_models():
        names=[p+d['name'] for key,p in [('wires','w:'),('registers','r:')] for d in raw[key] if d['cut']]
        for subset in itertools.product((False,True),repeat=len(names)):
            keep={n for n,present in zip(names,subset) if present}
            for mode in ('first-hit','waveform'): yield raw,keep,mode


def checked(raw,cert,limit=100000):
    meter=checker.Meter(limit)
    try:
        fn=checker.preservation if cert['kind']=='preservation' else checker.canonical
        fn(checker.Semantics(raw),copy.deepcopy(cert),meter)
        return dict(accepted=True,work=meter.result())
    except (checker.Rejected,checker.Incomplete,KeyError,TypeError,IndexError,RecursionError) as e:
        return dict(accepted=False,error=type(e).__name__,reason=str(e),work=meter.result())


def source_calls(raw,cert,limit=100000):
    m=checker.Semantics(raw); wc,_=free(raw,set(cert['retained'])); frames=[]; calls=[]
    replay_frames=2*(cert['time']+1) if cert['kind']=='counterexample' else 0
    original_frame,original_next=m.frame,m.next_state
    def frame(*args):
        result=original_frame(*args); index=len(frames)
        source=(index%2==0) if index<replay_frames else ((index-replay_frames)%(1+2**sum(w for _,w in wc))==0)
        frames.append((result[1],source)); return result
    def advance(context,cut):
        if any(context is obj and source for obj,source in frames): calls.append(id(context))
        return original_next(context,cut)
    m.frame,m.next_state=frame,advance; meter=checker.Meter(limit)
    try:
        (checker.preservation if cert['kind']=='preservation' else checker.canonical)(m,cert,meter)
        outcome='accepted'
    except (checker.Rejected,checker.Incomplete) as e: outcome=type(e).__name__
    return outcome,meter.result(),calls


class SuccessorRegression(unittest.TestCase):
    def test_complete_prefix_reference_and_semantic_counts(self):
        for raw,keep,mode in tiny_queries():
            status,cert=reference(raw,keep,mode)
            answer=producer.search(producer.Model(raw),keep,mode)
            self.assertEqual((answer['status'],answer['certificate']),(status,cert))
            if status=='invalid':
                cert['predecessors']=exclusion(raw,cert)
                self.assertEqual(producer.predecessor_certificate(producer.Model(raw),cert),cert['predecessors'])
            result=checked(raw,cert); self.assertTrue(result['accepted'],result)
            obs,succ,_=expected_work(raw,cert)
            self.assertEqual(result['work'],dict(observations=obs,successors=succ,limit=100000))

    def test_exact_semantic_cap_boundaries(self):
        for raw,keep,mode in list(tiny_queries())[::29]:
            _,cert=reference(raw,keep,mode)
            if cert['kind']=='counterexample': cert['predecessors']=exclusion(raw,cert)
            obs,succ,_=expected_work(raw,cert); total=obs+succ
            for cap in sorted({0,1,total-1,total,total+1}):
                result=checked(raw,cert,cap)
                self.assertEqual(result['accepted'],cap>=total)
                if cap<total:
                    self.assertEqual((result['error'],result['reason']),('Incomplete','checker semantic-obligation limit'))
                    self.assertEqual(result['work']['observations']+result['work']['successors'],max(cap,0))

    def test_lazy_source_evaluation_and_empty_tuple(self):
        for raw,keep,mode in list(tiny_queries())[::17]:
            _,cert=reference(raw,keep,mode)
            if cert['kind']=='counterexample': cert['predecessors']=exclusion(raw,cert)
            obs,succ,progressing=expected_work(raw,cert)
            outcome,work,calls=source_calls(raw,cert)
            self.assertEqual(outcome,'accepted'); self.assertEqual(len(calls),progressing)
            self.assertEqual(len(set(calls)),len(calls))
            self.assertEqual(work,dict(observations=obs,successors=succ,limit=100000))
        raw=[m for m in tiny_models() if m['id']=='empty-2-0'][0]
        _,cert=reference(raw,set(),'waveform')
        self.assertEqual(len(source_calls(raw,cert)[2]),2)  # () is cached, not a false sentinel.
        self.assertEqual(len(source_calls(raw,cert,1)[2]),0)  # First edge charge fails.
        raw['horizon']=0; _,cert=reference(raw,set(),'waveform')
        self.assertEqual(source_calls(raw,cert)[2],[])
        raw['horizon']=2; raw['done']=['const',1,1]
        _,cert=reference(raw,set(),'first-hit'); self.assertEqual(source_calls(raw,cert)[2],[])

    def test_snapshot_binding_and_mutation_between_calls(self):
        raw=list(tiny_models())[2]; keep={'r:q'}; _,cert=reference(raw,keep,'waveform')
        sem=checker.Semantics(raw); original=copy.deepcopy(raw)
        raw['registers'][0]['next']=['const',1,0]
        self.assertEqual(sem.data,original)
        fresh_status,fresh=reference(raw,keep,'waveform')
        self.assertEqual(producer.search(producer.Model(raw),keep,'waveform')['certificate'],fresh)
        if fresh_status=='valid': self.assertTrue(checked(raw,fresh)['accepted'])
        raw.clear(); raw.update(original); self.assertTrue(checked(raw,cert)['accepted'])


if __name__=='__main__': unittest.main()
