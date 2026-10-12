"""Canonical host replay with candidate-bound evidence reuse."""
from pathlib import Path
import copy, subprocess, sys, uuid

def pick_combined(output,read):
    records=[(p,read(p)) for p in (output/'final_result.json',output/'grade_result.json') if p.is_file()]
    if not records:return {},None
    if len(records)>1 and any(d!=records[0][1] for _,d in records[1:]):
        raise ValueError('Conflicting canonical result files')
    return records[0][1],str(records[0][0])


def validate_record(actor,run,tid,candidate,output,mode,current):
    m=actor.read(run/'validators'/tid/'validator_manifest.json')
    record=actor.read(output/'result.json',{})
    if record.get('status') not in ('PASS','FAIL'):return ['No completed behavior verdict'],record
    errors,_=actor.gate.audit_result(record,m,mode,record['status'],actor.read(output/'behavior.json',{}))
    expected=actor.runner.digest(actor.runner.hashes(candidate))
    if record.get('candidate_digest')!=expected:errors.append('Candidate fingerprint mismatch')
    if record.get('grader_files')!=current['grader']:errors.append('Grader fingerprint mismatch')
    if record.get('runner_sha256')!=current['runner']:errors.append('Runner fingerprint mismatch')
    if record.get('source_unchanged') is not True:errors.append('Execution changed candidate source')
    return errors,record


class HostReplay:
    def host_replay(self,lane,env):
        tid=lane['task_id'];run=Path(lane['run_root']);read=self.read;dump=self.dump
        if self.cancel.is_set():return {'task_id':tid,'status':'CANCELLED','checks':[]}
        context=read(lane['context']);source=Path(context['source_repo'])
        revision=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True,timeout=30).strip()
        dirty=subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True,timeout=30).strip()
        if revision!=context['source_revision'] or dirty:
            return {'task_id':tid,'status':'FAIL','reason':'Source identity/clean worktree differs','checks':[]}
        current=self.gate.current(run,tid)
        policy=self.cfg.get('resume_v3',{}).get(tid,{})
        prior_path=policy.get('verified_replay_reuse')
        if prior_path:
            prior=read(Path(prior_path),{})
            expected={'reference':('tasks_gt','full','PASS'),'start_baseline':('tasks','baseline','PASS'),'start_full':('tasks','full','FAIL')}
            ok=prior.get('status')=='PASS' and len(prior.get('checks',[]))==3 and {c.get('name') for c in prior['checks']}==set(expected)
            for c in prior.get('checks',[]) if ok else []:
                tree,mode,status=expected[c['name']];out=Path(c['result']).parent
                errors,record=validate_record(self,run,tid,run/tree/tid,out,mode,current)
                final,_=pick_combined(out,read)
                ok=ok and not errors and c.get('status')==status and c.get('canonical_status')==status and final.get('status')==status and c.get('exit_code')==c.get('canonical_exit_code')=={'PASS':0,'FAIL':1}[status]
                ok=ok and c.get('intended_target_failure',True) and c.get('preservation_passed',True)
            if ok:
                receipt=copy.deepcopy(prior);receipt['reused_verified_replay']=dict(path=prior_path,sha256=self.sha(Path(prior_path)),checked_utc=self.now(),basis='Current independent gate and candidate/grader/runner records revalidated; original executions preserved')
                dump(self.amendment/'replay_reuse'/(tid+'.json'),receipt)
                return receipt
        manifest=run/'validators'/tid/'validator_manifest.json';entry=manifest.parent/'validate.py';data=read(manifest)
        fresh=run/('host_final_replay_'+uuid.uuid4().hex[:12]);fresh.mkdir()
        checks=[]
        def finish(status,reason=None):
            result={'task_id':tid,'status':status,'checks':checks,'finished_utc':self.now(),'reference_fresh_render':True,'entrypoint':'canonical public validate.py','visual_judgment':'Existing independently reviewed candidate-bound receipt; no new visual judgment claimed','recovery_amendment':str(self.amendment)}
            if reason:result['reason']=reason
            dump(fresh/'host_replay.json',result);return result
        clean={k:v for k,v in env.items() if k not in ('CODEX_PROXY_TOKEN','CODEX_HOME')}
        with (fresh/'help.stdout.log').open('w') as out,(fresh/'help.stderr.log').open('w') as err:
            rc=self.run_process([sys.executable,str(entry),'--help'],run,clean,out,err,30,record=fresh/'help.process.json')
        if rc==130 or self.cancel.is_set():return finish('CANCELLED')
        if rc!=0:return finish('INFRA_ERROR' if rc==124 else 'FAIL','Canonical validator help failed; inspect entrypoint imports/interface')
        help_text=(fresh/'help.stdout.log').read_text();has_visual='--visual-review' in help_text
        if not all(flag in help_text for flag in ('--candidate','--output-dir','--mode','--render')):
            return finish('FAIL','Canonical entrypoint lacks the existing candidate/output/mode/render CLI contract')
        for name,tree,mode,expected in [('reference','tasks_gt','full','PASS'),('start_baseline','tasks','baseline','PASS'),('start_full','tasks','full','FAIL')]:
            output=fresh/(name+'_attempt_1');candidate=run/tree/tid;case_env=dict(clean)
            for var,sub in [('XDG_DATA_HOME','data'),('XDG_CONFIG_HOME','config'),('XDG_CACHE_HOME','cache')]:
                path=fresh/(name+'_runtime')/sub;path.mkdir(parents=True);case_env[var]=str(path)
            argv=[sys.executable,str(entry),'--candidate',str(candidate),'--output-dir',str(output),'--mode',mode,'--render']
            visual=run/read(run/'private'/tid/'visual_review.json')['receipt'] if name=='reference' else None
            if visual is not None and has_visual:argv+=['--visual-review',str(visual)]
            with (fresh/(name+'.stdout.log')).open('w') as out,(fresh/(name+'.stderr.log')).open('w') as err:
                rc=self.run_process(argv,run,case_env,out,err,self.cfg.get('host_verify_timeout_seconds',600),record=fresh/(name+'.process.json'))
            if rc==130 or self.cancel.is_set():return finish('CANCELLED')
            report=read(output/'result.json',{});canonical_rc=rc
            # Behavior-only public entrypoints still receive the SAME mandatory
            # candidate-bound visual combiner, never an assumed visual PASS.
            if not has_visual and rc in (0,1) and report.get('status') in ('PASS','FAIL'):
                argv=[sys.executable,str(self.batch/'runtime/grade.py'),'--manifest',str(manifest),'--candidate',str(candidate),'--output-dir',str(output),'--mode',mode,'--combine-existing']
                if visual is not None:argv+=['--visual-review',str(visual)]
                with (fresh/(name+'.combine.stdout.log')).open('w') as out,(fresh/(name+'.combine.stderr.log')).open('w') as err:
                    canonical_rc=self.run_process(argv,run,case_env,out,err,120,record=fresh/(name+'.combine.process.json'))
            if canonical_rc==130 or self.cancel.is_set():return finish('CANCELLED')
            combined,result_path=pick_combined(output,read)
            errors,report=validate_record(self,run,tid,candidate,output,mode,current)
            item={'name':name,'expected':expected,'status':report.get('status','ERROR'),'exit_code':rc,'canonical_status':combined.get('status','ERROR'),'canonical_exit_code':canonical_rc,'canonical_reason':combined.get('reason',[]),'result':str(output/'result.json'),'canonical_result':result_path,'audit_errors':errors,'attempt':1}
            if combined.get('candidate_digest')!=report.get('candidate_digest'):item['audit_errors'].append('Canonical verdict candidate binding mismatch')
            if name=='start_full':
                spec=read(run/'private'/tid/'task_spec.json');targets={r['id'] for r in spec['requirements'] if r['kind']=='target'};preserved={r['id'] for r in spec['requirements'] if r['kind']!='target'}
                item['intended_target_failure']=any(c.get('status')=='FAIL' and targets.intersection(c.get('R_ids',[])) for c in report.get('checks',[]))
                pchecks={k for k,v in data['checks'].items() if set(v['R_ids']) and set(v['R_ids'])<=preserved};observed={c['check_id']:c['status'] for c in report.get('checks',[])}
                item['preservation_passed']=all(observed.get(k)=='PASS' for k in pchecks)
            checks.append(item)
            if errors or rc not in (0,1) or canonical_rc not in (0,1) or not combined:
                # Retain the existing host-vs-task distinction: an interrupted
                # pre-engine execution is not evidence of a task behavior defect.
                status='INFRA_ERROR' if not report.get('execution') and (not report or report.get('status') in ('ERROR','TIMEOUT')) else 'FAIL'
                return finish(status,'Canonical replay did not complete required task checks; preserve logs and diagnose entrypoint/runtime evidence')
        if self.gate.current(run,tid)!=current:return finish('FAIL','Inputs changed during host replay')
        ok=all(c['status']==c['canonical_status']==c['expected'] and c['exit_code']==c['canonical_exit_code']=={'PASS':0,'FAIL':1}[c['expected']] and c.get('intended_target_failure',True) and c.get('preservation_passed',True) for c in checks)
        return finish('PASS' if ok else 'FAIL')
