import subprocess, json, sys, codecs

result = subprocess.run(
    ["node", r"E:\qclaw\resources\openclaw\config\skills\online-search\scripts\prosearch.cjs", '{"keyword":"qwenpaw"}'],
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace"
)
with open(r"C:\Users\yiseg\.qclaw\workspace\temp_search_out.txt", "w", encoding="utf-8") as f:
    f.write("STDOUT:\n" + result.stdout + "\n")
    f.write("STDERR:\n" + result.stderr + "\n")
    f.write("RC:" + str(result.returncode) + "\n")
print("Done")
