#!/usr/bin/env python3
"""Offline workflow repairs, append-only actual evidence, reports and recovery plans.

No network/auth or arbitrary Python execution. JSON bundles use the public library
arguments named in refs/acceptance-and-promotion.md. Controller owns live calls.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parent/'lib'))
import acceptance as evidence
import operation_outcomes as outcomes
import promotion
import workflow_repairs as repairs
import native_actions
import action_inventory
import decimal_procedure_adapter as decimal_adapter


def read(path):return json.loads(Path(path).read_text())


def atomic_write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    text=json.dumps(value,indent=2,allow_nan=False)+'\n'
    fd,tmp=tempfile.mkstemp(prefix=path.name+'.',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as file:file.write(text);file.flush();os.fsync(file.fileno())
        os.replace(tmp,path)
        directory=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['repair-contract','repair-manifest','repair-update','finalize-repair','formula-accounting',
        'secondary-input-hosts','published-mode','decimal-adapter','rebind-repair','matrix','record','reports','backup','promote','rollback','finalize-mutation','checkpoint','outcome','verify-outcome','public-native-actions','native-action-update','native-action-readback','qualify-public-selection'])
    parser.add_argument('--bundle',type=Path,help='JSON object of named library arguments')
    parser.add_argument('--source',type=Path);parser.add_argument('--state',type=Path)
    parser.add_argument('--out',required=True,type=Path);args=parser.parse_args()
    data=read(args.bundle) if args.bundle else {}
    evidence._no_secrets(data)
    if args.command=='repair-contract':
        if not args.source:parser.error('--source required')
        result=repairs.extract_workflow_repairs(args.source)
    elif args.command=='record' or args.command=='checkpoint':
        if not args.state:parser.error('--state required')
        if args.state.resolve()==args.out.resolve():parser.error('--out must differ from append-only --state')
        args.state.parent.mkdir(parents=True,exist_ok=True)
        with open(str(args.state)+'.lock','a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            ledger=read(args.state) if args.state.exists() else []
            result=(evidence.append_evidence(ledger,data['matrix'],data['capture']) if args.command=='record'
                else promotion.checkpoint_promotion(ledger,data['backup'],data['event']))
            atomic_write(args.state,result)
    else:
        functions={'public-native-actions':native_actions.emit_public_native_action_fragments,'native-action-update':repairs.prepare_native_action_update,
            'native-action-readback':repairs.verify_native_action_update_readback,'qualify-public-selection':action_inventory.qualify_public_selection_capture,
            'secondary-input-hosts':repairs.build_secondary_input_hosts,'published-mode':repairs.build_published_input_mode_program,'decimal-adapter':decimal_adapter.build_decimal_text_procedure_action,'repair-manifest':repairs.extend_repair_manifest,'repair-update':repairs.prepare_repair_update,
            'rebind-repair':repairs.rebind_after_repair,'finalize-repair':repairs.finalize_repair_update,'formula-accounting':repairs.account_formula_targets,
            'matrix':evidence.build_acceptance_matrix,'backup':promotion.build_promotion_backup,
            'promote':promotion.prepare_promotion,'rollback':promotion.prepare_rollback,
            'finalize-mutation':promotion.finalize_mutation,'outcome':outcomes.reconcile_operation,'verify-outcome':outcomes.verify_outcome_row}
        if args.command=='reports':
            reports=evidence.build_workflow_reports(**data);result={'reports':reports,'markdown':evidence.render_reports_markdown(reports)}
        else:result=functions[args.command](**data)
    evidence._no_secrets(result);atomic_write(args.out,result)


if __name__=='__main__':main()
