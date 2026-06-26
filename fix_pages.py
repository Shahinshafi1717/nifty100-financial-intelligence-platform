import os
pages=["p01_home","p02_profile","p03_screener","p04_peer","p05_trends","p06_sectors","p07_capital","p08_documents"]
for p in pages:
    path=f"src/dashboard/pages/{p}.py"
    if not os.path.exists(path):continue
    c=open(path,encoding="utf-8").read()
    c=c.replace("parents[3]","parents[2]")
    open(path,"w",encoding="utf-8").write(c)
    print(f"Fixed {p}")
