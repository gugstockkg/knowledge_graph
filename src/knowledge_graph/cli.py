"""One entry point for collection, extraction, graph creation and storage."""
import argparse,sys,runpy

def main(argv=None):
 args=list(sys.argv[1:] if argv is None else argv)
 commands={'collect':'knowledge_graph.ingestion.collection','ingest':'knowledge_graph.ingestion.cli','extract':'knowledge_graph.graph.ownership','graph':'knowledge_graph.graph.ownership','report':'knowledge_graph.graph.report','prepare':'knowledge_graph.storage.prepare_import','neo4j':'knowledge_graph.storage.manage','verify':'knowledge_graph.storage.verify','install-macos':'knowledge_graph.storage.install_macos','prices':'knowledge_graph.market.prices','market-link':'knowledge_graph.market.link'}
 if not args or args[0] in ['--help','-h']:
  parser=argparse.ArgumentParser(description='OpenDART → v0.1 evidence-linked graph → Neo4j')
  parser.add_argument('command',choices=sorted(commands),help='collect=date range; ingest=legacy API commands; extract/graph=bounded pilot; prepare=typed CSV; neo4j=start/stop/import/status; verify=live DB checks')
  parser.print_help();return 0
 command=args.pop(0)
 if command not in commands:raise SystemExit('Unknown command; use --help')
 original=sys.argv;sys.argv=[command]+args
 try:
  if command=='collect':
   from .ingestion.collection import entry
   return entry(args)
  runpy.run_module(commands[command],run_name='__main__')
 except (OSError,ValueError,RuntimeError) as error:
  # Exceptions must not disclose configured credentials.
  import os
  message=str(error)
  for key in ['OPENDART_API_KEY','NEO4J_PASSWORD']:
   if os.environ.get(key):message=message.replace(os.environ[key],'[REDACTED]')
  print('오류: '+message,file=sys.stderr);return 2
 finally:sys.argv=original
 return 0

if __name__=='__main__':raise SystemExit(main())
