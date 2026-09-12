import argparse
import json
import os
from pathlib import Path
from .transform import json_value


def main():
    # Arquivo local simples KEY=VALUE, sem expansão ou execução de conteúdo.
    env = Path('.env')
    if env.exists():
        for line in env.read_text(encoding='utf-8-sig').splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                key,value = line.split('=',1)
                os.environ.setdefault(key.strip(),value.strip())
    parser = argparse.ArgumentParser(description='AdventureWorks DW incremental')
    parser.add_argument('command',choices=['restore','prepare-source','init','run','verify','report'])
    parser.add_argument('--resync',action='store_true',help='Reconciliação completa explícita; preserva SKs')
    parser.add_argument('--fail-before-checkpoint',action='store_true',help='Injeta falha para demonstração de rollback')
    args = parser.parse_args()
    from . import setup, pipeline, evidence
    if args.command=='restore':
        setup.restore()
    elif args.command=='prepare-source':
        setup.prepare_source()
    elif args.command=='init':
        setup.init_dw()
    elif args.command=='run':
        print(json.dumps(pipeline.run(args.resync,args.fail_before_checkpoint),default=json_value,indent=2,ensure_ascii=False))
    elif args.command=='verify':
        evidence.verify()
    elif args.command=='report':
        evidence.report()


if __name__=='__main__':
    main()
