#!/usr/bin/env python3

import argparse,time
from schedule import every,run_pending
from cl import create_app,get_db
from cl.jobs import run_due_jobs

app=create_app()

def run(force=False):
    with app.app_context(): 
        return run_due_jobs(get_db(),force=force)

def main():
    parser=argparse.ArgumentParser(description="CL scheduled Craigslist search jobs")
    parser.add_argument("--force",action="store_true",help="run every enabled job immediately")
    args=parser.parse_args()
    if args.force: 
        print(f"Ran {run(True)} Craigslist jobs")
        return
    every().minute.do(run)
    print("Starting CL scheduler")
    while True: 
        run_pending()
        time.sleep(1)
if __name__=="__main__": main()
