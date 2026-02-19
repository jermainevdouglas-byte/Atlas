# Git Helper for PowerShell
# Add this to your PowerShell profile for easier git commands

# Option 1: Add to PowerShell Profile (Recommended)
# 1. Open PowerShell as Admin
# 2. Run: $PROFILE
# 3. Copy the path shown
# 4. Open that file in notepad
# 5. Add these functions at the end:

function git { &"D:\AtlasSimple\Git\bin\git.exe" @args }

# Then use git normally: git status, git push, etc.

---

# Option 2: Create a Batch File Shortcut
# Create: D:\git.bat
# Content:
@echo off
"D:\AtlasSimple\Git\bin\git.exe" %*

# Then use: git status, git push, etc. from any PowerShell

---

# Option 3: Quick Alias for Current Session
# Run this in PowerShell:

function git { &"D:\AtlasSimple\Git\bin\git.exe" @args }

# Then use: git status, git push, etc.

---

# USAGE EXAMPLES

# After setting up alias, use normally:

git status                 # Check status
git log --oneline -5       # View commits
git add .                  # Stage all changes
git commit -m "Message"    # Commit
git push origin main       # Push to GitHub
git pull origin main       # Pull from GitHub
git branch -a              # List branches
git checkout -b feature    # Create new branch
git diff                   # View uncommitted changes
