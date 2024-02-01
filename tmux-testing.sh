#!/bin/sh

# TODO: when running ssh, set the identity file to point to the key for the server

# NOTE: this needs to be run from the 18749-Project directory
# NOTE: passing any cmdline args will skip ssh-ing and run it locally

# NOTE: `tmux ls` will show all current sessions
# NOTE: `tmux attach-session -t "reliable"

# General TMUX settings
tmux unbind C-b
tmux unbind C-Space
tmux set -g prefix C-Space
tmux bind-key C-Space send-prefix

tmux set -g base-index 1
tmux set -g pane-base-index 1

tmux set -g mouse on



# setting up naming
class="reliable"
c_window="client"
s_window="server"

lines="$(tput lines)"
columns="$(tput cols)"

# delete existing session if it has the same name
sessions=$(tmux list-sessions -F "#{session_name}")
for session in $sessions; do
    if [ $class = $session ]; then
        tmux kill-session -t $class
    fi
done



# making session and windows
tmux new-session -d -x "$columns" -y "$lines" -s "$class" -n "$s_window" 'bash' # make new session with server window
tmux new-window -t "$class" -n "$c_window" 'bash' # add on the client window to the session



# splits for server window
#    vertical splits
tmux split-window -h -t "$class:$s_window" -p 66 'bash'


#    horizontal splits inside center column
tmux split-window -v -t "$class:$s_window.1" -p 50 'bash'
tmux split-window -v -t "$class:$s_window.3" -p 69 'bash'
tmux split-window -v -t "$class:$s_window.4" -p 50 'bash'

#    vertical splits inside three sections of center column
tmux split-window -h -t "$class:$s_window.3" -p 50 'bash'
tmux split-window -h -t "$class:$s_window.5" -p 50 'bash'
tmux split-window -h -t "$class:$s_window.7" -p 50 'bash'

# renaming splits
tmux select-pane -t "$class:$s_window.1" -T "rep-mngr"
tmux select-pane -t "$class:$s_window.2" -T "gfd"
tmux select-pane -t "$class:$s_window.3" -T "lfd1"
tmux select-pane -t "$class:$s_window.4" -T "s1"
tmux select-pane -t "$class:$s_window.5" -T "lfd2"
tmux select-pane -t "$class:$s_window.6" -T "s2"
tmux select-pane -t "$class:$s_window.7" -T "lfd3"
tmux select-pane -t "$class:$s_window.8" -T "s3"


# splits for client window
tmux split-window -h -t "$class:$c_window" -p 66 'bash'
tmux split-window -h -t "$class:$c_window" -p 50 'bash'
tmux select-pane -t "$class:$c_window.1" -T "c1"
tmux select-pane -t "$class:$c_window.2" -T "c2"
tmux select-pane -t "$class:$c_window.3" -T "c3"



# ssh into the servers and go into proper folders
#    there doesn't seem to be any way to reference panes by their name :((
if [ $# -eq 0 ]; then
    tmux send-keys -t "$class:$s_window.1" "ssh s0.749" C-m "cd 18749-Project" C-m
    tmux send-keys -t "$class:$s_window.2" "ssh s0.749" C-m "cd 18749-Project" C-m
    tmux send-keys -t "$class:$s_window.3" "ssh s1.749" C-m "cd 18749-Project" C-m
    tmux send-keys -t "$class:$s_window.4" "ssh s1.749" C-m "cd 18749-Project" C-m
    tmux send-keys -t "$class:$s_window.5" "ssh s2.749" C-m "cd 18749-Project" C-m
    tmux send-keys -t "$class:$s_window.6" "ssh s2.749" C-m "cd 18749-Project" C-m
    tmux send-keys -t "$class:$s_window.7" "ssh s3.749" C-m "cd 18749-Project" C-m
    tmux send-keys -t "$class:$s_window.8" "ssh s3.749" C-m "cd 18749-Project" C-m
fi

# go into pane-specific folder and type in run cmds
tmux send-keys -t "$class:$s_window.1" "cd RM"     C-m "clear" C-m "python3 rm.py -m passive"
tmux send-keys -t "$class:$s_window.2" "cd GFD"    C-m "clear" C-m "python3 gfd.py"
tmux send-keys -t "$class:$s_window.3" "cd LFD"    C-m "clear" C-m "python3 lfd.py -n 1"
tmux send-keys -t "$class:$s_window.4" "cd server" C-m "clear" C-m "python3 server.py -n 1 -m passive"
tmux send-keys -t "$class:$s_window.5" "cd LFD"    C-m "clear" C-m "python3 lfd.py -n 2"
tmux send-keys -t "$class:$s_window.6" "cd server" C-m "clear" C-m "python3 server.py -n 2 -m passive"
tmux send-keys -t "$class:$s_window.7" "cd LFD"    C-m "clear" C-m "python3 lfd.py -n 3"
tmux send-keys -t "$class:$s_window.8" "cd server" C-m "clear" C-m "python3 server.py -n 3 -m passive"


tmux send-keys -t "$class:$c_window.1" "cd client" C-m "clear" C-m "python3 client.py -n 1 -m passive"
tmux send-keys -t "$class:$c_window.2" "cd client" C-m "clear" C-m "python3 client.py -n 2 -m passive"
tmux send-keys -t "$class:$c_window.3" "cd client" C-m "clear" C-m "python3 client.py -n 3 -m passive"

