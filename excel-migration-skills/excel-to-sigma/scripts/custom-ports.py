#!/usr/bin/env python3
"""Offline reviewed-port authoring. Writes artifacts; never executes Sigma/VBA/SQL."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent/'lib'))
import custom_ports as ports


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    def command(name,fields):
        p=sub.add_parser(name)
        for field in fields:p.add_argument('--'+field,required=True,type=Path)
        p.add_argument('--out',required=True,type=Path)
        return p
    p=command('emit-python',[]);p.add_argument('--model-binding',required=True)
    p.add_argument('--column-maps',type=Path)
    p=command('prepare',['base-manifest','base-receipt','module','fixture','expected','reviews','scope'])
    p=command('prepare-update',['manifest','receipt','current','sources']);p.add_argument('--column-maps',type=Path)
    p.add_argument('--phase',choices=['code-first','solver-outputs','guard-output'],default='code-first')
    for name in ('previous-phase','output-evidence','phase-context','consumed-phases','adoption-evidence'):p.add_argument('--'+name,type=Path)
    p=command('finalize-update',['proposal','current','dry-run']);p.add_argument('--consumed',type=Path,required=True)
    p.add_argument('--reviewed-warning-hash')
    p.add_argument('--phase-context',type=Path)
    command('procedure',['contract','arguments'])
    command('prepare-goal-actions',['manifest','receipt','current','initial-proposal','binding','request','model','result'])
    args=parser.parse_args()
    read=lambda name:json.loads(getattr(args,name).read_text())
    if args.command=='emit-python':
        result=ports.emit_python_programs(args.model_binding,column_maps=read('column_maps') if args.column_maps else None)
    elif args.command=='prepare':
        result=ports.build_custom_port_plan(read('base_manifest'),read('base_receipt'),module_path=args.module,
            fixture_path=args.fixture,expected_path=args.expected,reviews=read('reviews'),scope=read('scope'))
    elif args.command=='prepare-update':
        result=ports.prepare_port_update(read('manifest'),read('receipt'),read('current'),read('sources'),
            column_maps=read('column_maps') if args.column_maps else None,phase=args.phase,
            previous_phase=read('previous_phase') if args.previous_phase else None,
            output_evidence=read('output_evidence') if args.output_evidence else None,
            phase_context=read('phase_context') if args.phase_context else None,
            consumed_phases=read('consumed_phases') if args.consumed_phases else (),
            adoption_evidence=read('adoption_evidence') if args.adoption_evidence else None)
    elif args.command=='finalize-update':
        result=ports.finalize_port_update(read('proposal'),read('current'),read('dry_run'),
            consumed_proposals=read('consumed'),reviewed_warning_hash=args.reviewed_warning_hash,
            fresh_phase_context=read('phase_context') if args.phase_context else None)
    elif args.command=='prepare-goal-actions':
        model=read('model')
        result=ports.prepare_goal_action_update(read('manifest'),read('receipt'),read('current'),read('initial_proposal'),
            read('binding'),read('request'),model['actuals'],model['inputs'],model['definitions'],read('result'))
    else:result=ports.build_procedure_action(read('contract'),read('arguments'))
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':main()
