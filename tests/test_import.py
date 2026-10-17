import traceback
import sys
try:
    import backend.main
    with open("traceback.txt", "w") as f:
        f.write("IMPORT SUCCESSFUL\n")
except BaseException as e:
    with open("traceback.txt", "w") as f:
        f.write(f"Exception: {str(e)}\n")
        traceback.print_exc(file=f)
