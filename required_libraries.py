"""
Installs any third-party packages the MESI simulator needs.
Run once:  python required_libraries.py
"""

import subprocess
import sys
import os


REQUIRED = ['tabulate']


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    req = os.path.join(here, 'requirements.txt')

    if os.path.exists(req):
        args = [sys.executable, '-m', 'pip', 'install', '-r', req]
    else:
        args = [sys.executable, '-m', 'pip', 'install'] + REQUIRED

    print(f"Running: {' '.join(args)}")
    try:
        subprocess.check_call(args)
    except subprocess.CalledProcessError as e:
        print(f"\npip install failed (exit {e.returncode}).")
        print("If you use multiple Python versions, try:  py -m pip install -r requirements.txt")
        sys.exit(1)

    print("\nDone. Try running:")
    print("   python test_simulator.py")
    print("   python experiments.py")


if __name__ == '__main__':
    main()
