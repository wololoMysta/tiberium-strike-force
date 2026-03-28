# run_mp.py – launches server + 2 local clients in separate processes
import subprocess
import sys
import time
import os

DIR = os.path.dirname(os.path.abspath(__file__))
PY  = sys.executable

def main():
    procs = []
    log_files = []
    try:
        # Start server
        print("Starting server...")
        sf = open(os.path.join(DIR, "log_server.txt"), "w")
        log_files.append(sf)
        server = subprocess.Popen([PY, os.path.join(DIR, "server.py")],
                                  stdout=sf, stderr=sf)
        procs.append(server)
        time.sleep(2)  # give server time to bind

        # Start client 1
        print("Starting client 1 (Player 0)...")
        c1f = open(os.path.join(DIR, "log_client1.txt"), "w")
        log_files.append(c1f)
        c1 = subprocess.Popen([PY, os.path.join(DIR, "client.py"),
                                "--host", "localhost"],
                               stdout=c1f, stderr=c1f)
        procs.append(c1)
        time.sleep(1)

        # Start client 2
        print("Starting client 2 (Player 1)...")
        c2f = open(os.path.join(DIR, "log_client2.txt"), "w")
        log_files.append(c2f)
        c2 = subprocess.Popen([PY, os.path.join(DIR, "client.py"),
                                "--host", "localhost"],
                               stdout=c2f, stderr=c2f)
        procs.append(c2)

        print("All processes launched. Close any window to stop.")
        # Wait for any process to exit
        while all(p.poll() is None for p in procs):
            time.sleep(0.5)

    except KeyboardInterrupt:
        pass
    finally:
        print("Shutting down...")
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for f in log_files:
            f.close()
        # Print exit codes
        time.sleep(1)
        for i, p in enumerate(procs):
            name = ['server', 'client1', 'client2'][i] if i < 3 else f'proc{i}'
            print(f"  {name} exit code: {p.poll()}")
        # Print log tails
        for name in ('log_server.txt', 'log_client1.txt', 'log_client2.txt'):
            path = os.path.join(DIR, name)
            if os.path.exists(path):
                print(f"\n=== {name} (last 30 lines) ===")
                with open(path) as f:
                    lines = f.readlines()
                for line in lines[-30:]:
                    print(line, end='')

if __name__ == "__main__":
    main()
