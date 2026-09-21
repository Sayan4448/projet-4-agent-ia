"""PyInstaller entry point for AgentScreen.exe (native desktop UI)."""
from agent_screen.gui import main

if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test-browser":
        from agent_screen.diagnostics import browser_check
        sys.exit(0 if browser_check(sys.argv[2]) else 1)
    else:
        main()
