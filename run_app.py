"""PyInstaller entry point for AgentScreen.exe (native desktop UI)."""

if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test-browser":
        # keep the GUI stack out of the smoke test: a broken import there
        # would kill the windowed exe silently on a console-less runner
        from agent_screen.diagnostics import browser_check
        sys.exit(0 if browser_check(sys.argv[2]) else 1)
    from agent_screen.gui import main
    main()
