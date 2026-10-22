#!/usr/bin/env python3
"""Offline Forecast Save-scenario definition, evidence, completion and SDK plans.

This command never calls Sigma, enables a sequence, marks a workflow published,
or treats a constructed program as persisted action admission.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent/"lib"))
from forecast_scenario import (build_save_definition,adapt_save_rest_capture,
    adapt_save_primary_capture,plan_save_completion,render_save_completion_candidate)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    commands=p.add_subparsers(dest="command",required=True)
    definition=commands.add_parser("define")
    definition.add_argument("--manifest",required=True)
    definition.add_argument("--binding",required=True)
    definition.add_argument("--audit-mapping",required=True)
    rest=commands.add_parser("adapt-rest")
    rest.add_argument("--definition",required=True)
    rest.add_argument("--role",required=True,choices=("operations","saved"))
    rest.add_argument("--target",required=True)
    for name in ("bindings","request","job","download-request","request-provenance",
                 "rows","timezone","source-before","source-after"):
        rest.add_argument("--"+name,required=True)
    primary=commands.add_parser("adapt-primary")
    primary.add_argument("--definition",required=True)
    primary.add_argument("--target",required=True)
    for name in ("binding","query","source-before","source-after"):
        primary.add_argument("--"+name,required=True)
    plan=commands.add_parser("plan")
    for name in ("definition","operation-id","operations","saved","primary","target",
                 "control-value"):
        plan.add_argument("--"+name,required=True)
    name=plan.add_mutually_exclusive_group(required=True)
    name.add_argument("--name-control")
    name.add_argument("--name-control-null",action="store_true")
    render=commands.add_parser("render")
    for name in ("definition","current","bindings","completion-plan","operations","saved","primary"):
        render.add_argument("--"+name,required=True)
    render.add_argument("--phase",required=True,choices=("mark","clear"))
    for sub in commands.choices.values():sub.add_argument("--out",required=True)
    return p


def main(argv=None):
    args=parser().parse_args(argv)
    if args.command=="define":
        result=build_save_definition(read(args.manifest),read(args.binding),read(args.audit_mapping))
    elif args.command=="adapt-rest":
        result=adapt_save_rest_capture(read(args.definition),role=args.role,target=read(args.target),
            **{name+"_path":getattr(args,name) for name in ("bindings","request","job","rows","timezone")},
            download_request_path=args.download_request,request_provenance_path=args.request_provenance,
            source_before_path=args.source_before,source_after_path=args.source_after)
    elif args.command=="adapt-primary":
        result=adapt_save_primary_capture(read(args.definition),target=read(args.target),
            binding_path=args.binding,query_path=args.query,
            source_before_path=args.source_before,source_after_path=args.source_after)
    elif args.command=="plan":
        result=plan_save_completion(read(args.definition),args.operation_id,read(args.operations),
            read(args.saved),read(args.primary),read(args.target),
            name_control=None if args.name_control_null else args.name_control,
            control_value=args.control_value)
    else:
        result=render_save_completion_candidate(read(args.definition),read(args.current),read(args.bindings),
            read(args.completion_plan),operations=read(args.operations),saved=read(args.saved),
            primary=read(args.primary),phase=args.phase)
    Path(args.out).write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return 0


if __name__=="__main__":raise SystemExit(main())
