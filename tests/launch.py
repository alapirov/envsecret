import importlib.machinery, importlib.util, sys, os
sys.dont_write_bytecode=True
here=os.path.dirname(os.path.abspath(__file__))
ld=importlib.machinery.SourceFileLoader("es",os.path.join(here,"..","envsecret")); spec=importlib.util.spec_from_loader("es",ld); es=importlib.util.module_from_spec(spec); ld.exec_module(es)
es.SECURITY=os.path.join(here,"fake_security"); es.OSASCRIPT=os.path.join(here,"fake_osascript"); es.PBCOPY=os.path.join(here,"fake_pbcopy")
es.KEYCHAIN="/fake/login.keychain-db"; es.CONFIG=os.path.join(os.environ.get("FAKE_HOME", here),"config")
sys.argv=["envsecret"]+sys.argv[1:]
es.main()
