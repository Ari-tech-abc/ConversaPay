from pathlib import Path
p=Path("backend/routers/widget.py")
t=p.read_text(encoding="utf-8")
old="version\\": \\"2.0.0\\""
new="version\\": \\"2.5.0\\""
t=t.replace(old,new)
p.write_text(t,encoding="utf-8")
print("updated widget.py")
