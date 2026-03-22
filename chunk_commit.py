import subprocess
import os

def run_cmd(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    return result.stdout.strip()

def main():
    # Make sure we get all untracked files
    untracked = run_cmd('git ls-files --others --exclude-standard')
    # If the user already added things to index but didn't commit:
    cached = run_cmd('git ls-files --cached')
    
    files_set = set(f for f in untracked.split('\n') if f)
    files_set.update(f for f in cached.split('\n') if f)
    
    # Remove files that are already part of a commit (if any, though fresh repo should only have .gitignore if we just committed it)
    committed = run_cmd('git ls-tree -r HEAD --name-only') if run_cmd('git rev-parse HEAD 2>nul') else ""
    for c in committed.split('\n'):
        if c in files_set:
            files_set.remove(c)
            
    files = list(files_set)
    files.sort()
    
    if not files:
        print("No files to commit.")
        return
        
    total_commits = 60
    
    if len(files) < total_commits:
        total_commits = len(files)
        
    chunk_size, remainder = divmod(len(files), total_commits)
    
    print(f"Total files: {len(files)}, Target Commits: {total_commits}")

    start_idx = 0
    for i in range(total_commits):
        current_chunk_size = chunk_size + 1 if i < remainder else chunk_size
        end_idx = start_idx + current_chunk_size
        chunk = files[start_idx:end_idx]
        
        if not chunk:
            break
            
        print(f"Commit {i+1}/{total_commits}: Adding {len(chunk)} files...")
        
        batch_size = 50
        for j in range(0, len(chunk), batch_size):
            batch = chunk[j:j+batch_size]
            quoted_batch = ['"' + f + '"' for f in batch]
            add_cmd = 'git add ' + ' '.join(quoted_batch)
            subprocess.run(add_cmd, shell=True, check=True)
            
        commit_msg = f"Add project files part {i+1}/{total_commits}"
        subprocess.run(['git', 'commit', '-m', commit_msg], check=True)
        
        start_idx = end_idx
        
    print("Done chunking commits. Ready to push.")

if __name__ == "__main__":
    main()
