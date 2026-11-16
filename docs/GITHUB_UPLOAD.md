# Putting this project on GitHub, step by step

Everything below is for Windows. Do the steps in order.

> **Read this first.** `api_key.txt` holds your secret aisstream.io key.
> It is already listed in `.gitignore`, so git will leave it out — but
> check for it anyway in step 5 before you push. Never upload the key.

---

## Step 1. Install git

Git is not installed on this computer yet. Pick one:

- **Easy:** open the Microsoft Store, search for **Git**, install it.
- **Command line:** open PowerShell and run:

  ```
  winget install Git.Git
  ```

- **Manually:** download it from <https://git-scm.com/download/win> and
  run the installer (the defaults are fine).

Then **close and reopen the terminal** and check it worked:

```
git --version
```

## Step 2. Tell git who you are

Run these once, with your own name and email (use the same email as
your GitHub account):

```
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

## Step 3. Create an empty repository on GitHub

1. Go to <https://github.com/new> (sign in if asked).
2. Repository name: `fundy-vessel-tracker` (this is the name the README uses).
3. Leave it **Public** (or Private if you prefer).
4. **Important:** do NOT tick "Add a README", "Add .gitignore" or
   "Choose a license" — this project already has those files, and
   adding them on GitHub causes a conflict.
5. Click **Create repository**.

GitHub shows you a page with a URL like
`https://github.com/YOUR_USERNAME/fundy-vessel-tracker.git` — copy it.

## Step 4. Turn the project folder into a git repository

In the terminal, go to the project folder:

```
cd "C:\Users\Ashut\Downloads\Fundy Vessel"
```

Then run:

```
git init
git add .
git commit -m "Initial commit"
```

## Step 5. CHECK that the secret is not included

Run:

```
git status
```

Then look at what `git add` staged earlier:

```
git ls-files
```

- You **must not** see `api_key.txt`, `data/raw/`, `data/sample/`,
  `outputs/` or `outputs_sample/` in the file list.
- If `api_key.txt` IS listed, run `git rm --cached api_key.txt`, check
  that `api_key.txt` appears in `.gitignore`, commit again, and then
  **change your key on aisstream.io anyway** to be safe.

## Step 6. Connect to GitHub and upload

Use the URL you copied in step 3:

```
git remote add origin https://github.com/YOUR_USERNAME/fundy-vessel-tracker.git
git branch -M main
git push -u origin main
```

The first push opens a browser window asking you to sign in to GitHub
(that is the Git Credential Manager, installed with git). Sign in once
and future pushes happen without asking.

Refresh the repository page in your browser — you should see all the
project files.

## Step 7. Pushing changes later

After you edit files:

```
git add .
git commit -m "Say what you changed"
git push
```

If `run_pipeline.py` produced new results, note that `outputs/` is
gitignored on purpose — results are rebuilt, not stored. If you want a
specific result picture (like `map.png`) visible on GitHub, copy it to
`docs/images/` first and add it to the README.

---

## Problems

| Problem | What to do |
|---|---|
| `git is not recognized` | Close and reopen the terminal after installing. Still broken? Reinstall and tick "Git from the command line" during setup. |
| Push asks for a password | GitHub no longer accepts passwords. Sign in through the browser window that pops up, or create a Personal Access Token at <https://github.com/settings/tokens> and paste that as the password. |
| `remote origin already exists` | Run `git remote set-url origin YOUR_URL` instead of `git remote add`. |
| Push rejected because the GitHub repo has commits | You created the repo with a README/.gitignore. Run `git pull origin main --rebase`, then push again. |
| Accidentally committed `api_key.txt` | Run `git rm --cached api_key.txt`, commit, push, then **delete the key on aisstream.io and make a new one** — treat it as exposed. |
| Prefer a point-and-click tool | Install **GitHub Desktop** (<https://desktop.github.com>) — it does the same thing with buttons: "Add local repository", "Publish repository". |
