import subprocess
import sys
print(sys.executable)
from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    subprocess.Popen([
        sys.executable,
        r"C:\Users\a493353\Desktop\Lans Galos\Lot Tracking System\launch_system.py"
    ])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
