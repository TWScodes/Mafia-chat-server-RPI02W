from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from datetime import datetime
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Simulated data stores (use a database for production)
messages = []  # List of posted messages
banned_ips = set()  # Set of banned IPs
# Example of how to structure the `usernames` dictionary
usernames = {}

admin_ips = ["127.0.0.1"]  # Example IPs
mafias = {}  # Stores mafia name -> details (emoji, title, members, leader)
mafia_members = {}  # This should be initialized here to avoid the NameError
mafia_notifications = {}  # Stores mafia name -> list of pending join requests
last_username_change = {}  # Track when users last changed their username
mafia_chat_messages = {}  # Dictionary to store mafia chat messages by mafia name

user_ip = ""
user_message_log = defaultdict(list)
# Limit constants
MAX_MESSAGES_PER_MINUTE = 50
TIME_FRAME = timedelta(minutes=1)  # 1 minute time window

# Username constraints
USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 20
USERNAME_PATTERN = r'^[a-zA-Z0-9_]+$'

def validate_username(username):
    """Check if the username is valid: letters, numbers, underscores, and length 3-20 characters."""
    return bool(re.match(r'^[a-zA-Z0-9_]{3,20}$', username))

@app.route('/api/messages')
def api_messages():
    return jsonify(messages)

@app.before_request
def get_user_ip():
    global user_ip
    user_ip = request.remote_addr  # Get the user's IP address
    
@app.route("/", methods=["GET", "POST"])
def home():
    user_ip = request.remote_addr

    # Ensure that the user has a username, otherwise redirect them to set one
    if user_ip not in usernames:
        return redirect(url_for('set_username'))

    # Handle new messages
    if request.method == "POST":
        message = request.form.get("message")
        if message:
            # Get mafia info from usernames structure
            mafia_name = usernames.get(user_ip, {}).get('mafia')
            mafia_info = None
            if mafia_name:
                mafia_info = {
                    'name': mafia_name,
                    'emoji': mafias.get(mafia_name, {}).get('emoji', '')
                }

            # Get the current timestamp
            current_time = datetime.now()

            # Clean up the user message log by removing messages older than 1 minute
            user_message_log[user_ip] = [timestamp for timestamp in user_message_log[user_ip] if current_time - timestamp <= TIME_FRAME]

            # Check if the user has exceeded the message limit
            if len(user_message_log[user_ip]) >= MAX_MESSAGES_PER_MINUTE:
                flash("You have reached the limit of 50 messages per minute.", "error")
                return redirect(url_for("home"))

            # Add the current timestamp to the user's message log
            user_message_log[user_ip].append(current_time)

            # Append the new message to the list with mafia info
            messages.append({
                "id": len(messages) + 1,
                "message": message,
                "ip": user_ip,
                "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                "username": usernames.get(user_ip, {}).get('username', "Anonymous"),
                "mafia": mafia_info,  # Include mafia info in the message
            })

    return render_template("index.html", messages=messages, admin_ips=admin_ips)

@app.route("/set_username", methods=["GET", "POST"])
def set_username():
    user_ip = request.remote_addr
    
    # If user already has a username, redirect to home
    if user_ip in usernames:
        return redirect(url_for("home"))

    if request.method == "POST":
        # Get the username from the form
        username = request.form.get("username")
        mafia_name = request.form.get("mafia_name")  # Assuming a mafia is selected (optional)

        # Validate the username
        if validate_username(username):
            # Store the username and mafia info in the usernames structure
            usernames[user_ip] = {'username': username, 'mafia': mafia_name}
            return redirect(url_for("home"))
        else:
            return "Invalid username. Only letters, numbers, and underscores are allowed. Length should be between 3 and 20 characters.", 400

    return render_template("set_username.html", mafias=mafias)

def validate_username(username):
    """Validate the username"""
    if len(username) < USERNAME_MIN_LENGTH or len(username) > USERNAME_MAX_LENGTH:
        return False
    if not re.match(USERNAME_PATTERN, username):
        return False
    return True

@app.route('/delete/<int:message_id>', methods=['POST'])
def delete_message(message_id):
    user_ip = request.remote_addr

    # Check if user is an admin
    if user_ip not in admin_ips:
        return "Forbidden", 403

    # Find the message by ID and delete it
    message_to_delete = next((msg for msg in messages if msg["id"] == message_id), None)

    if message_to_delete:
        # Delete the message from the list
        messages.remove(message_to_delete)

        # Optionally, flash a success message
        flash("Message deleted successfully.", "success")
    else:
        # If the message doesn't exist, flash an error message
        flash("Message not found.", "error")

    # Redirect back to home after deleting the message
    return redirect(url_for('home'))


@app.route("/ban/<int:message_id>", methods=["POST"])
def ban_user(message_id):
    user_ip = request.remote_addr

    # Check if user is an admin
    if user_ip not in admin_ips:
        return "Forbidden", 403

    # Find the message by ID
    message = next((msg for msg in messages if msg["id"] == message_id), None)

    if message:
        # Add the user's IP to the banned_ips set
        banned_ips.add(message["ip"])

        # Optional: You might want to log this event or display a message to confirm banning
        flash("User has been banned.", "success")
    else:
        # Optional: If message doesn't exist, you can display a warning message
        flash("Message not found.", "error")

    # Redirect to home after banning
    return redirect(url_for("home"))

@app.route('/mafias', methods=['GET', 'POST'])
def mafias_page():
    user_ip = request.remote_addr

    # If the user is part of a mafia
    if user_ip in mafia_members:
        user_mafia = mafia_members[user_ip]['mafia']
        user_rank = mafia_members[user_ip]['rank']
        return render_template(
            'mafia_members.html',  # Change to the correct template
            mafias=mafias,
            mafia_name=user_mafia,
            user_rank=user_rank,
            mafia_members=mafia_members,
            mafia_notifications=mafia_notifications
        )

    # If the user is not part of a mafia and tries to create one
    if request.method == 'POST':
        mafia_name = request.form['mafia_name']
        mafia_emoji = request.form['mafia_emoji']
        mafia_title = request.form['mafia_title']

        # Mafia name length validation
        if len(mafia_name) > 50:
            return "Mafia name is too long. Limit is 50 characters.", 400

        # Save mafia details in the dictionary
        mafias[mafia_name] = {
            'emoji': mafia_emoji,
            'title': mafia_title,
            'members': [],
            'leader': user_ip
        }

        # Update mafia_members with the new mafia
        mafia_members[user_ip] = {
            'mafia': mafia_name,
            'rank': 'Mafia Boss'
        }

        # Redirect to the mafia page (now the user is a mafia boss)
        return redirect('/mafias')

    # If the user is not in a mafia, show the mafia creation page
    return render_template('mafias.html', mafias=mafias)

@app.route('/join_mafia/<mafia_name>', methods=['POST'])
def join_mafia(mafia_name):
    user_ip = request.remote_addr

    if user_ip in mafia_members:
        return "You are already part of a mafia.", 400

    if mafia_name not in mafias:
        return "Mafia not found.", 404

    mafia = mafias[mafia_name]
    if len(mafia['members']) >= 10:  # Limiting mafia size to 10 members
        return "This mafia is full.", 400

    mafia_members[user_ip] = {
        'mafia': mafia_name,
        'rank': 'Member'
    }

    mafia['members'].append(user_ip)

    # Notify mafia leader about new join request
    mafia_notifications.setdefault(mafia['leader'], []).append({
        'type': 'join_request',
        'user_ip': user_ip
    })

    return redirect('/')

@app.route("/remove_mafia/<mafia_name>", methods=["POST"])
def remove_mafia(mafia_name):
    user_ip = request.remote_addr
    if user_ip in admin_ips:
        mafias.pop(mafia_name, None)
    return redirect(url_for("mafias_page"))

@app.route("/add_member/<mafia_name>", methods=["POST"])
def add_member(mafia_name):
    user_ip = request.remote_addr
    if user_ip in admin_ips:
        # Add logic to add a member to the mafia
        pass
    return redirect(url_for("mafias_page"))

@app.route('/leave_mafia', methods=['POST'])
def leave_mafia():
    user_ip = request.remote_addr
    if user_ip not in mafia_members:
        return "You are not part of any mafia.", 400

    mafia_name = mafia_members[user_ip]['mafia']
    del mafia_members[user_ip]
    mafias[mafia_name]['members'].remove(user_ip)

    return redirect('/mafias')

@app.route('/remove_user_from_mafia/<user_ip>', methods=['POST'])
def remove_user_from_mafia(user_ip):
    # Retrieve the mafia name of the user being removed
    mafia_name = mafia_members.get(user_ip, {}).get('mafia')
    
    # Check if the mafia exists and the user is part of a mafia
    if mafia_name:
        mafia_leader = mafias[mafia_name]['leader']
        
        # Check if the current user is the mafia leader or has permission to remove users
        if request.remote_addr == mafia_leader or 'can_ban' in MAFIA_RANKS[mafia_members[request.remote_addr]['rank']]:
            # Remove the user from the mafia and delete them from mafia members
            mafia_members.pop(user_ip, None)
            mafias[mafia_name]['members'].remove(user_ip)
            
            # Optionally: Handle banning the user, e.g., add to banned list or other actions
            mafias[mafia_name].setdefault('banned_users', []).append(user_ip)
            
            return redirect(f'/mafias/{mafia_name}/members')  # Redirect to mafia members page
    return "Unauthorized or User not found.", 403  # If unauthorized or user not found, return error

@app.route('/kick_user/<user_ip>', methods=['POST'])
def kick_user(user_ip):
    mafia_name = mafia_members.get(user_ip, {}).get('mafia')
    if mafia_name:
        mafia_leader = mafias[mafia_name]['leader']
        if request.remote_addr == mafia_leader or 'can_kick' in MAFIA_RANKS[mafia_members[request.remote_addr]['rank']]:
            del mafia_members[user_ip]
            mafias[mafia_name]['members'].remove(user_ip)
            return redirect('/mafias')
    return "Unauthorized or User not found.", 403

@app.route('/unmute_user/<user_ip>', methods=['POST'])
def unmute_user(user_ip):
    mafia_name = mafia_members.get(user_ip, {}).get('mafia')
    if mafia_name:
        mafia_leader = mafias[mafia_name]['leader']
        if request.remote_addr == mafia_leader or 'can_mute' in MAFIA_RANKS[mafia_members[request.remote_addr]['rank']]:
            muted_users.pop(user_ip, None)
            return redirect('/mafias')
    return "Unauthorized or User not found.", 403

@app.route('/accept_request/<user_ip>', methods=['POST'])
def accept_request(user_ip):
    mafia_name = mafias[mafia_members[user_ip]['mafia']]['name']
    mafia_notifications[mafia_name].remove({
        'type': 'join_request',
        'user_ip': user_ip
    })

    mafia_members[user_ip] = {
        'mafia': mafia_name,
        'rank': 'Member'
    }
    mafias[mafia_name]['members'].append(user_ip)

    return redirect('/')

@app.route('/deny_request/<user_ip>', methods=['POST'])
def deny_request(user_ip):
    mafia_name = mafias[mafia_members[user_ip]['mafia']]['name']
    mafia_notifications[mafia_name].remove({
        'type': 'join_request',
        'user_ip': user_ip
    })
    return redirect('/')

@app.route('/mafia_search', methods=['GET'])
def mafia_search():
    # List all active mafias
    results = mafias  # mafias is a dictionary storing mafia details

    return render_template('mafia_search.html', results=results)

@app.route('/change_mafia_title/<mafia_name>', methods=['GET', 'POST'])
def change_mafia_title(mafia_name):
    if mafia_members[request.remote_addr]['rank'] == 'Mafia Boss':
        if request.method == 'POST':
            new_title = request.form['title']
            if len(new_title) > 50:
                return "Title too long.", 400
            mafias[mafia_name]['title'] = new_title
            return redirect('/mafias')

        return render_template('change_title.html', mafia_name=mafia_name)
    return "You are not the Mafia Boss", 403

@app.route('/change_mafia_emoji/<mafia_name>', methods=['GET', 'POST'])
def change_mafia_emoji(mafia_name):
    if mafia_members[request.remote_addr]['rank'] == 'Mafia Boss':
        if request.method == 'POST':
            new_emoji = request.form['emoji']
            mafias[mafia_name]['emoji'] = new_emoji
            return redirect('/mafias')

        return render_template('change_emoji.html', mafia_name=mafia_name)
    return "You are not the Mafia Boss", 403

@app.route('/mafia_chat/<mafia_name>', methods=['GET', 'POST'])
def mafia_chat(mafia_name):
    if mafia_name not in mafias:
        return redirect(url_for('home'))  # Redirect to the home page if mafia doesn't exist

    # Get the mafia's members and check if the user is part of it
    if user_ip not in mafia_members.get(mafia_name, []):
        return redirect(url_for('home'))  # Redirect to home if the user is not a member

    # Fetch mafia messages (can be stored in a dictionary with mafia_name as the key)
    mafia_messages = mafia_chat_messages.get(mafia_name, [])

    if request.method == 'POST':
        message = request.form.get('message')
        if message:
            mafia_chat_messages.setdefault(mafia_name, []).append({
                'user_ip': user_ip,
                'message': message,
                'timestamp': datetime.now()
            })
            return redirect(url_for('mafia_chat', mafia_name=mafia_name))

    return render_template('mafia_chat.html', mafia_name=mafia_name, messages=mafia_messages)

@app.route("/banned")
def banned():
    return render_template("banned.html")

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
