#!/usr/bin/env python3
"""Prepare, bind and emit reviewed native macro action construction programs.

This command never executes VBA, contacts Sigma, or invokes an action sequence.
Restage the returned manifest through input-sync.py before schema/action emission.
Production remains BLOCKED; --staging-review enables only the exact reviewed test
workbook/version so the parent runtime harness can perform published acceptance.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent/'lib'))
from macro_behavior import analyze_macro_source
from native_actions import (build_native_action_plan,validate_native_action_plan,
    bind_native_action_target,emit_action_schema,checkpoint_action_schema,
    emit_native_action_program,audit_native_action_readback,emit_input_identity_projection)


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def write(path,value):
    Path(path).write_text(json.dumps(value,indent=2,default=str)+'\n',encoding='utf-8')


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    commands=p.add_subparsers(dest='command',required=True)
    prepare=commands.add_parser('prepare')
    prepare.add_argument('source')
    for name in ('base-manifest','base-receipt','presentation-bindings','contents','input-readbacks','decisions'):
        prepare.add_argument('--'+name,required=True)
    prepare.add_argument('--macro',action='append',required=True)
    for command in ('bind-target','emit-schema','emit-actions','emit-projection'):
        c=commands.add_parser(command)
        c.add_argument('--manifest',required=True);c.add_argument('--receipt',required=True)
        if command!='emit-schema':c.add_argument('--contents',required=True)
        if command=='bind-target':c.add_argument('--input-readbacks',required=True)
        if command=='emit-schema':
            c.add_argument('--feature',required=True);c.add_argument('--current-columns')
        if command=='emit-projection':
            c.add_argument('--feature',required=True);c.add_argument('--destination-page',required=True);c.add_argument('--name',required=True)
        if command=='emit-actions':
            c.add_argument('--bindings',required=True);c.add_argument('--staging-review')
    checkpoint=commands.add_parser('checkpoint-schema')
    for name in ('extension-plan','created-columns','before','after'):
        checkpoint.add_argument('--'+name,required=True)
    checkpoint.add_argument('--result-version',required=True,type=int)
    audit=commands.add_parser('audit-readback')
    audit.add_argument('--expected',required=True);audit.add_argument('--capture',required=True)
    for sub in commands.choices.values():sub.add_argument('--out',required=True)
    return p


def main(argv=None):
    a=parser().parse_args(argv)
    if a.command=='prepare':
        result=build_native_action_plan(workbook_source=a.source,base_manifest=read(a.base_manifest),
            base_receipt=read(a.base_receipt),presentation_bindings=read(a.presentation_bindings),
            current_contents=read(a.contents),input_readbacks=read(a.input_readbacks),
            macro_analyses=[analyze_macro_source(path) for path in a.macro],decisions=read(a.decisions))
    elif a.command=='bind-target':
        result=bind_native_action_target(read(a.manifest),read(a.receipt),
            current_contents=read(a.contents),input_readbacks=read(a.input_readbacks))
    elif a.command=='emit-schema':
        result=emit_action_schema(read(a.manifest),read(a.receipt),a.feature,
            current_columns=read(a.current_columns) if a.current_columns else None)
    elif a.command=='checkpoint-schema':
        result=checkpoint_action_schema(read(a.extension_plan),read(a.created_columns),
            result_version=a.result_version,before=read(a.before),after=read(a.after))
    elif a.command=='emit-projection':
        result=emit_input_identity_projection(read(a.manifest),read(a.receipt),a.feature,
            current_contents=read(a.contents),destination_page=a.destination_page,name=a.name)
    elif a.command=='emit-actions':
        result=emit_native_action_program(read(a.manifest),read(a.receipt),read(a.bindings),
            current_contents=read(a.contents),staging_review=read(a.staging_review) if a.staging_review else None)
    else:
        result=audit_native_action_readback(read(a.expected),read(a.capture))
    write(a.out,result)
    return 1 if result.get('status')=='FAILED' else 0


if __name__=='__main__':raise SystemExit(main())
