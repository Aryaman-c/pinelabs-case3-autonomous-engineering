#!/usr/bin/env python3
"""
Stage 1 Automated Verification Script
Checks static deliverables, hardening specs, and (if available) live container runtime.
"""

import os
import shutil
import subprocess
import sys

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"

def print_pass(msg):
    print(f"{GREEN}[PASS]{RESET} {msg}")

def print_fail(msg):
    print(f"{RED}[FAIL]{RESET} {msg}")

def print_info(msg):
    print(f"{CYAN}[INFO]{RESET} {msg}")

def print_warn(msg):
    print(f"{YELLOW}[WARN]{RESET} {msg}")

def verify_stage_1():
    print("=" * 65)
    print("  Stage 1 Verification: Container Infrastructure & Hardening")
    print("=" * 65)
    
    all_passed = True
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 1. File existence checks
    required_files = [
        "docker-compose.yml",
        "Dockerfile.sandbox",
        "Dockerfile.orchestrator",
        "requirements.orchestrator.txt",
        "requirements.sandbox.txt",
        ".env.example",
        ".env",
        "Makefile",
    ]
    
    print("\n--- 1. Deliverables File Check ---")
    for f in required_files:
        path = os.path.join(base_dir, f)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            print_pass(f"Found non-empty deliverable: {f}")
        else:
            print_fail(f"Missing or empty file: {f}")
            all_passed = False
            
    # Required directories
    required_dirs = ["orchestrator", "api", "sample-repo", "data", "tests", "evals"]
    for d in required_dirs:
        path = os.path.join(base_dir, d)
        if os.path.isdir(path):
            print_pass(f"Found directory: {d}/")
        else:
            print_fail(f"Missing directory: {d}/")
            all_passed = False

    # 2. Hardening specifications check
    print("\n--- 2. Hardening & Blueprint Spec Validation ---")
    
    # Check docker-compose.yml
    dc_path = os.path.join(base_dir, "docker-compose.yml")
    if os.path.exists(dc_path):
        with open(dc_path, "r", encoding="utf-8") as fp:
            dc_content = fp.read()
        
        checks = [
            ("network_mode: none", "Sandbox egress network disabled (network_mode: none)"),
            ("cap_drop:\n      - ALL", "Linux capabilities fully dropped (cap_drop: ALL)"),
            ("pids_limit: 64", "PID limit enforced (pids_limit: 64)"),
            ("mem_limit: 512m", "Memory limit enforced (mem_limit: 512m)"),
            ('user: "1000:1000"', "Non-root user mapped (user: 1000:1000)"),
        ]
        for pattern, label in checks:
            if pattern in dc_content:
                print_pass(label)
            else:
                print_fail(f"Missing hardening in docker-compose.yml: {pattern}")
                all_passed = False

    # Check Dockerfile.sandbox
    df_sandbox_path = os.path.join(base_dir, "Dockerfile.sandbox")
    if os.path.exists(df_sandbox_path):
        with open(df_sandbox_path, "r", encoding="utf-8") as fp:
            df_content = fp.read()
            
        sb_checks = [
            ("useradd -u 1000", "Sandbox user created with UID 1000"),
            ("USER agent", "USER set to non-root agent"),
            ("requirements.sandbox.txt", "Installs requirements.sandbox.txt"),
        ]
        for pattern, label in sb_checks:
            if pattern in df_content:
                print_pass(label)
            else:
                print_fail(f"Missing configuration in Dockerfile.sandbox: {pattern}")
                all_passed = False

    # Check requirements.sandbox.txt
    req_sb_path = os.path.join(base_dir, "requirements.sandbox.txt")
    if os.path.exists(req_sb_path):
        with open(req_sb_path, "r", encoding="utf-8") as fp:
            req_content = fp.read()
        for pkg in ["pytest", "pytest-json-report", "bandit", "ruff"]:
            if pkg in req_content:
                print_pass(f"Sandbox dependencies include: {pkg}")
            else:
                print_fail(f"Sandbox missing dependency: {pkg}")
                all_passed = False

    # Check requirements.orchestrator.txt
    req_orch_path = os.path.join(base_dir, "requirements.orchestrator.txt")
    if os.path.exists(req_orch_path):
        with open(req_orch_path, "r", encoding="utf-8") as fp:
            orch_content = fp.read()
        for pkg in ["langgraph", "aiosqlite", "google-genai", "fastapi", "uvicorn", "docker", "pip-audit"]:
            if pkg in orch_content:
                print_pass(f"Orchestrator dependencies include: {pkg}")
            else:
                print_fail(f"Orchestrator missing dependency: {pkg}")
                all_passed = False

    # 3. Docker runtime checks
    print("\n--- 3. Container Runtime Environment Check ---")
    docker_bin = shutil.which("docker")
    if not docker_bin:
        print_warn("Docker CLI is not detected in your PATH.")
        print_info("To run live container checks, install and start Docker Desktop for Windows.")
        print_info("Manual runtime verification commands once Docker is active:")
        print("    1. docker compose build")
        print("    2. docker compose up -d")
        print("    3. docker inspect autonomous-eng-org-sandbox --format '{{.HostConfig.NetworkMode}}'")
        print("    4. docker exec -u agent autonomous-eng-org-sandbox whoami")
    else:
        print_pass(f"Docker binary located at: {docker_bin}")
        try:
            res = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                print_pass("Docker daemon is running.")
                print_info("Executing live container verification...")
                # Run docker compose build
                build_res = subprocess.run(["docker", "compose", "build"], capture_output=True, text=True)
                if build_res.returncode == 0:
                    print_pass("docker compose build succeeded.")
                else:
                    print_fail(f"docker compose build failed:\n{build_res.stderr}")
                    all_passed = False

                # Run docker compose up -d
                up_res = subprocess.run(["docker", "compose", "up", "-d"], capture_output=True, text=True)
                if up_res.returncode == 0:
                    print_pass("docker compose up -d succeeded.")
                else:
                    print_fail(f"docker compose up -d failed:\n{up_res.stderr}")
                    all_passed = False

                # Inspect network mode
                inspect_res = subprocess.run(
                    ["docker", "inspect", "autonomous-eng-org-sandbox", "--format", "{{.HostConfig.NetworkMode}}"],
                    capture_output=True, text=True
                )
                net_mode = inspect_res.stdout.strip()
                if net_mode == "none":
                    print_pass("Network isolation confirmed: network_mode == 'none'")
                else:
                    print_fail(f"Expected network_mode 'none', got '{net_mode}'")
                    all_passed = False

                # Exec whoami
                whoami_res = subprocess.run(
                    ["docker", "exec", "-u", "agent", "autonomous-eng-org-sandbox", "whoami"],
                    capture_output=True, text=True
                )
                user = whoami_res.stdout.strip()
                if user == "agent":
                    print_pass("Sandbox non-root user confirmed: user == 'agent'")
                else:
                    print_fail(f"Expected user 'agent', got '{user}'")
                    all_passed = False
            else:
                print_warn("Docker daemon is not responding (Docker Desktop may be stopped).")
        except Exception as e:
            print_warn(f"Docker execution check encountered: {e}")

    print("\n" + "=" * 65)
    if all_passed:
        print_pass("Stage 1 Static & Blueprint Specifications: 100% COMPLETE")
    else:
        print_fail("Stage 1 has missing or non-compliant deliverables.")
    print("=" * 65)

if __name__ == "__main__":
    verify_stage_1()
