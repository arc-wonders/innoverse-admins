import streamlit as st
import pymongo
from datetime import datetime, timezone
from authlib.integrations.requests_client import OAuth2Session
import urllib.parse
import pandas as pd
from bson import ObjectId
import plotly.express as px
import plotly.graph_objects as go
import os
import hashlib
import secrets

import threading, requests, time

def keep_alive():
    while True:
        try:
            url = os.getenv("RENDER_URL")  # 👈 must be set in Render env vars
            if url:
                requests.get(url, timeout=10)
                print(f"[HealthCheck] Pinged {url}")
        except Exception as e:
            print(f"[HealthCheck] Failed: {e}")
        time.sleep(600)  # 10 minutes


# Set page config first
st.set_page_config(
    page_title="Innoverse Admin Portal",
    page_icon="🚀",
    layout="wide"
)

# MongoDB connection
MONGO_URI = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "Cluster0")

@st.cache_resource
def init_connection():
    if not MONGO_URI:
        st.error("Missing MONGO_URI. Set it in Render → Environment.")
        st.stop()
    return pymongo.MongoClient(MONGO_URI)

client = init_connection()
db = client[DATABASE_NAME]


# Collections
admin_col = db.admins
users_col = db.users
tasks_col = db.tasks
submissions_col = db.submissions
forums_col = db.forums
forum_comments_col = db.forum_comments
sessions_col = db.admin_sessions

# Track mapping
TRACKS = {
    "ai": "AI/ML",
    "webdev": "Web Development", 
    "dsa": "Data Structures & Algorithms",
    "app": "App Development"
}

# OAuth2 session for Google authentication
def get_google_auth(state=None, token=None):
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    redirect_uri = os.getenv("OAUTH_REDIRECT_URI")

    return OAuth2Session(
        client_id=client_id,
        scope="openid email profile",
        redirect_uri=redirect_uri,
        state=state,
        token=token
    )


def create_session_token():
    """Create a secure session token"""
    return secrets.token_urlsafe(32)

def authenticate_admin(username, password):
    """Authenticate admin and create secure session"""
    admin = admin_col.find_one({"username": username, "password": password})
    if admin:
        # Create a secure session token
        session_token = create_session_token()
        session_data = {
            "token": session_token,
            "admin_id": admin["_id"],
            "username": username,
            "created_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc).timestamp() + 86400  # 24 hours
        }
        
        # Store session in database
        sessions_col.update_one(
            {"admin_id": admin["_id"]},  # find by admin
            {"$set": session_data},
            upsert=True
        )
        
        # Update last login + increment login counter
        admin_col.update_one(
            {"_id": admin["_id"]},
            {
                "$set": {"last_login": datetime.now(timezone.utc)},
                "$inc": {"login_count": 1}  # 👈 add or increment counter
            }
        )
        
        return session_token
    return None

def validate_session(session_token):
    """Validate session token"""
    if not session_token:
        return False
    
    session = sessions_col.find_one({"token": session_token})
    if not session:
        return False
    
    # Check if session has expired
    current_time = datetime.now(timezone.utc).timestamp()
    if current_time > session["expires_at"]:
        # Clean up expired session
        sessions_col.delete_one({"token": session_token})
        return False
    
    # Extend session expiry on valid use
    sessions_col.update_one(
        {"token": session_token},
        {"$set": {"expires_at": current_time + 86400}}  # Extend by 24 hours
    )
    
    return session["username"]

def logout_admin(session_token):
    """Logout admin and clean up session"""
    if session_token:
        sessions_col.delete_one({"token": session_token})

def cleanup_expired_sessions():
    """Clean up expired sessions"""
    current_time = datetime.now(timezone.utc).timestamp()
    sessions_col.delete_many({"expires_at": {"$lt": current_time}})

def main():

    # --- Start health check thread once ---
    if "health_thread" not in st.session_state:
        st.session_state["health_thread"] = True
        threading.Thread(target=keep_alive, daemon=True).start()

    # Clean up expired sessions periodically
    cleanup_expired_sessions()
    
    # Initialize session state
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "admin_username" not in st.session_state:
        st.session_state.admin_username = None
    if "session_token" not in st.session_state:
        st.session_state.session_token = None

    # --- Google OAuth callback handler ---
    params = st.query_params
    if "code" in params and not st.session_state.authenticated:
        # Rebuild full redirect URL with query string
        query_string = urllib.parse.urlencode({k: v for k, v in params.items()})
        full_url = f"{os.getenv('OAUTH_REDIRECT_URI')}?{query_string}"
    
        google = get_google_auth(state=st.session_state.get("oauth_state"))
        token = google.fetch_token(
            "https://oauth2.googleapis.com/token",
            authorization_response=full_url,
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
            redirect_uri=os.getenv("OAUTH_REDIRECT_URI"),
            auth=None   # 👈 IMPORTANT FIX
        )

    
        google = get_google_auth(token=token)
        resp = google.get("https://www.googleapis.com/oauth2/v2/userinfo")
        profile = resp.json()
    
        email = profile.get("email")
        name = profile.get("name")
    
        # Check if this email is an admin in Mongo
        admin = admin_col.find_one({"email": email})
        if admin:
            session_token = create_session_token()
            session_data = {
                "token": session_token,
                "admin_id": admin["_id"],
                "username": admin["username"],
                "created_at": datetime.now(timezone.utc),
                "expires_at": datetime.now(timezone.utc).timestamp() + 86400  # 24h
            }
        
            # Store session in DB
            # Upsert session → only 1 per admin
            sessions_col.update_one(
                {"admin_id": admin["_id"]},
                {"$set": session_data},
                upsert=True
            )
            
            # Update last login + increment login counter
            admin_col.update_one(
                {"_id": admin["_id"]},
                {
                    "$set": {"last_login": datetime.now(timezone.utc)},
                    "$inc": {"login_count": 1}
                }
            )
            
        
            # Set session state
            st.session_state.authenticated = True
            st.session_state.admin_username = admin["username"]
            st.session_state.session_token = session_token
        
            # Clear query params so code doesn’t keep firing
            st.query_params.clear()
            st.rerun()
        else:
            st.error("Your Google account is not authorized as admin.")
        
    # --- End OAuth callback handler ---


    # --- Validate session ---
    if st.session_state.session_token:
        username = validate_session(st.session_state.session_token)
        if username:
            st.session_state.authenticated = True
            st.session_state.admin_username = username
        else:
            # Invalid session, clear state
            st.session_state.authenticated = False
            st.session_state.admin_username = None
            st.session_state.session_token = None
    # --- End session validation ---

    # --- Show login or dashboard ---
    if not st.session_state.authenticated:
        login_page()
    else:
        admin_dashboard()

def login_page():
    st.title("🚀 Innoverse Admin Portal")
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.subheader("Admin Login")

        # Google login only
        google_auth = get_google_auth()
        authorization_url, state = google_auth.create_authorization_url(
            "https://accounts.google.com/o/oauth2/v2/auth"
        )
        
        # Save state in session
        if "oauth_state" not in st.session_state:
            st.session_state["oauth_state"] = state
        
        # Login button (stays in same tab)
        st.markdown(
            f'<a href="{authorization_url}" target="_self">'
            f'<button style="width:100%;padding:10px;background:#4285F4;color:white;'
            f'border:none;border-radius:5px;font-size:16px">Sign in with Google</button>'
            f'</a>',
            unsafe_allow_html=True
        )
      
def admin_dashboard():
    st.title("🚀 Innoverse Admin Dashboard")
    
    # Sidebar
    st.sidebar.title(f"Welcome, {st.session_state.admin_username}!")
    
    if st.sidebar.button("Logout"):
        logout_admin(st.session_state.session_token)
        st.session_state.authenticated = False
        st.session_state.admin_username = None
        st.session_state.session_token = None
        st.rerun()
    
    st.sidebar.markdown("---")
    
    # Navigation
    page = st.sidebar.selectbox(
        "Navigate to:",
        ["📊 Dashboard", "👥 Users", "📝 Tasks", "📄 Submissions", "💬 Forums", "📈 Analytics"]
    )
    
    if page == "📊 Dashboard":
        dashboard_overview()
    elif page == "👥 Users":
        users_management()
    elif page == "📝 Tasks":
        tasks_management()
    elif page == "📄 Submissions":
        submissions_management()
    elif page == "💬 Forums":
        forums_management()
    elif page == "📈 Analytics":
        analytics_page()

def dashboard_overview():
    st.header("📊 Dashboard Overview")
    
    # Key metrics
    total_users = users_col.count_documents({})
    total_tasks = tasks_col.count_documents({})
    total_submissions = submissions_col.count_documents({})
    total_forums = forums_col.count_documents({})
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Users", total_users)
    with col2:
        st.metric("Total Tasks", total_tasks)
    with col3:
        st.metric("Total Submissions", total_submissions)
    with col4:
        st.metric("Total Forums", total_forums)
    
    st.markdown("---")
    
    # Recent activity
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Recent Users")
        recent_users = list(users_col.find({}).sort("created_at", -1).limit(5))
        for user in recent_users:
            track_name = TRACKS.get(user.get('profile', {}).get('coding_track', ''), 'No track')
            st.write(f"• {user['name']} - {track_name}")
    
    with col2:
        st.subheader("Recent Submissions")
        recent_submissions = list(submissions_col.find({}).sort("submitted_at", -1).limit(5))
        for sub in recent_submissions:
            user = users_col.find_one({"_id": sub["user_id"]})
            task = tasks_col.find_one({"_id": sub["task_id"]})
            st.write(f"• {user['name'] if user else 'Unknown'} - {task['title'] if task else 'Unknown Task'} - {sub['status']}")

def users_management():
    st.header("👥 Users Management")
    
    # User statistics by track
    track_stats = {}
    for track_id, track_name in TRACKS.items():
        count = users_col.count_documents({"profile.coding_track": track_id})
        track_stats[track_name] = count
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Users by Track")
        for track, count in track_stats.items():
            st.metric(track, count)
    
    with col2:
        st.subheader("Track Distribution")
        if track_stats:
            fig = px.pie(values=list(track_stats.values()), names=list(track_stats.keys()))
            st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    
    # User list
    st.subheader("All Users")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        track_filter = st.selectbox("Filter by Track", ["All"] + list(TRACKS.values()))
    with col2:
        status_filter = st.selectbox("Filter by Status", ["All", "Active", "Inactive"])
    
    # Build query
    query = {}
    if track_filter != "All":
        track_id = [k for k, v in TRACKS.items() if v == track_filter][0]
        query["profile.coding_track"] = track_id
    if status_filter == "Active":
        query["is_active"] = True
    elif status_filter == "Inactive":
        query["is_active"] = False
    
    users = list(users_col.find(query).sort("created_at", -1))
    
    if users:
        users_data = []
        for user in users:
            users_data.append({
                "Name": user["name"],
                "Email": user["email"],
                "Track": TRACKS.get(user.get("profile", {}).get("coding_track", ""), "Unknown"),
                "Points": user.get("stats", {}).get("points", 0),
                "Tasks Completed": user.get("stats", {}).get("tasks_completed", 0),
                "Status": "Active" if user.get("is_active", True) else "Inactive",
                "Join Date": user["created_at"].strftime("%Y-%m-%d") if user.get("created_at") and hasattr(user["created_at"], 'strftime') else "Unknown"
            })
        
        df = pd.DataFrame(users_data)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No users found matching the criteria.")

def tasks_management():
    st.header("📝 Tasks Management")
    
    # Task creation form
    with st.expander("➕ Create New Task"):
        with st.form("create_task"):
            col1, col2 = st.columns(2)
            
            with col1:
                title = st.text_input("Task Title")
                track = st.selectbox("Track", ["ai", "webdev", "dsa", "app"], format_func=lambda x: TRACKS[x])
                difficulty = st.selectbox("Difficulty", ["beginner", "intermediate", "advanced"])
                points = st.number_input("Points", min_value=1, value=100)
            
            with col2:
                due_date = st.date_input("Due Date")
                task_type = st.selectbox("Type", ["individual", "team"])
                is_active = st.checkbox("Active", value=True)
            
            description = st.text_area("Description")
            requirements = st.text_area("Requirements (one per line)")
            
            if st.form_submit_button("Create Task"):
                if title and description:
                    req_list = [req.strip() for req in requirements.split('\n') if req.strip()]
                    
                    task_data = {
                        "title": title,
                        "description": description,
                        "due_date": datetime.combine(due_date, datetime.min.time()).replace(tzinfo=timezone.utc),
                        "points": points,
                        "is_active": is_active,
                        "team_id": None,
                        "type": task_type,
                        "difficulty": difficulty,
                        "track": track,
                        "requirements": req_list,
                        "created_by": st.session_state.admin_username,
                        "created_at": datetime.now(timezone.utc),
                        "updated_at": datetime.now(timezone.utc)
                    }
                    
                    tasks_col.insert_one(task_data)
                    st.success("Task created successfully!")
                    st.rerun()
                else:
                    st.error("Title and description are required!")
    
    # Individual task assignment form
    with st.expander("👤 Assign Task to Individual User"):
        st.subheader("Select Assignment Type")
        assignment_type = st.radio("Choose assignment type:", 
                                 ["Assign Existing Task", "Create Custom Task"], 
                                 horizontal=True)
        
        if assignment_type == "Assign Existing Task":
            # Get all users first (outside the form for search)
            all_users = list(users_col.find({}, {"_id": 1, "name": 1, "email": 1}))
            
            # User search outside form
            st.subheader("🔍 Find User")
            search_query = st.text_input("Search users by name or email", key="user_search_existing_outside")
            
            # Filter users based on search
            if search_query:
                filtered_users = [
                    user for user in all_users 
                    if search_query.lower() in user['name'].lower() or 
                       search_query.lower() in user['email'].lower()
                ]
                
                if filtered_users:
                    st.write(f"**Found {len(filtered_users)} matching users:**")
                    for user in filtered_users[:5]:  # Show max 5 results
                        st.write(f"• **{user['name']}** - {user['email']}")
                else:
                    st.write("No users found matching your search.")
            
            st.markdown("---")
            
            # Existing task assignment
            with st.form("assign_existing_task"):
                col1, col2 = st.columns(2)
                
                with col1:
                    # Get all active tasks
                    active_tasks = list(tasks_col.find({"is_active": True}))
                    if active_tasks:
                        task_options = {str(task["_id"]): f"{task['title']} ({TRACKS.get(task.get('track', ''), task.get('track', 'Unknown'))})" for task in active_tasks}
                        selected_task_id = st.selectbox("Select Task", options=list(task_options.keys()), 
                                                       format_func=lambda x: task_options[x])
                    else:
                        st.warning("No active tasks available")
                        selected_task_id = None
                
                with col2:
                    # User selection - show all users or filtered ones
                    st.write("**Select User:**")
                    display_users = filtered_users if search_query and filtered_users else all_users[:20]
                    
                    if display_users:
                        user_options = {str(user["_id"]): f"{user['name']} ({user['email']})" for user in display_users}
                        selected_user_id = st.selectbox(f"Available Users ({len(display_users)})", 
                                                       options=list(user_options.keys()), 
                                                       format_func=lambda x: user_options[x],
                                                       key="user_select_existing")
                    else:
                        st.warning("No users available")
                        selected_user_id = None
                
                assignment_note = st.text_area("Assignment Note (optional)", 
                                             placeholder="Add any specific instructions for this user...",
                                             key="note_existing")
                
                submit_existing = st.form_submit_button("Assign Existing Task", use_container_width=True)
                
                if submit_existing:
                    if selected_task_id and selected_user_id and active_tasks:
                        # Check if already assigned
                        existing_assignment = db.task_assignments.find_one({
                            "task_id": ObjectId(selected_task_id),
                            "user_id": ObjectId(selected_user_id)
                        })
                        
                        if not existing_assignment:
                            assignment_data = {
                                "task_id": ObjectId(selected_task_id),
                                "user_id": ObjectId(selected_user_id),
                                "assigned_by": st.session_state.admin_username,
                                "assigned_at": datetime.now(timezone.utc),
                                "note": assignment_note,
                                "status": "assigned",
                                "assignment_type": "existing"
                            }
                            
                            db.task_assignments.insert_one(assignment_data)
                            
                            # Get task and user details for success message
                            task_title = [task['title'] for task in active_tasks if str(task['_id']) == selected_task_id][0]
                            user_name = user_options[selected_user_id]
                            
                            st.success(f"Task '{task_title}' assigned to {user_name} successfully!")
                            st.rerun()
                        else:
                            st.error("This task is already assigned to this user!")
                    else:
                        st.error("Please select both a task and a user!")
        
        else:  # Create Custom Task
            # Get all users first (outside the form for search)
            all_users = list(users_col.find({}, {"_id": 1, "name": 1, "email": 1}))
            
            # User search outside form
            st.subheader("🔍 Find User")
            search_query_custom = st.text_input("Search users by name or email", key="user_search_custom_outside")
            
            # Filter users based on search
            if search_query_custom:
                filtered_users_custom = [
                    user for user in all_users 
                    if search_query_custom.lower() in user['name'].lower() or 
                       search_query_custom.lower() in user['email'].lower()
                ]
                
                if filtered_users_custom:
                    st.write(f"**Found {len(filtered_users_custom)} matching users:**")
                    for user in filtered_users_custom[:5]:  # Show max 5 results
                        st.write(f"• **{user['name']}** - {user['email']}")
                else:
                    st.write("No users found matching your search.")
            
            st.markdown("---")
            
            with st.form("assign_custom_task"):
                st.subheader("Create & Assign Custom Task")
                
                # User search and selection
                col1, col2 = st.columns(2)
                
                with col1:
                    # Custom task details
                    custom_title = st.text_input("Custom Task Title")
                    custom_track = st.selectbox("Track", ["ai", "webdev", "dsa", "app"], 
                                              format_func=lambda x: TRACKS[x], key="custom_track")
                    custom_difficulty = st.selectbox("Difficulty", ["beginner", "intermediate", "advanced"], 
                                                   key="custom_difficulty")
                    custom_points = st.number_input("Points", min_value=1, value=100, key="custom_points")
                    custom_due_date = st.date_input("Due Date", key="custom_due_date")
                
                with col2:
                    # User selection - show all users or filtered ones
                    st.write("**Select User:**")
                    display_users_custom = filtered_users_custom if search_query_custom and filtered_users_custom else all_users[:20]
                    
                    if display_users_custom:
                        user_options_custom = {str(user["_id"]): f"{user['name']} ({user['email']})" for user in display_users_custom}
                        selected_user_id_custom = st.selectbox(f"Available Users ({len(display_users_custom)})", 
                                                             options=list(user_options_custom.keys()), 
                                                             format_func=lambda x: user_options_custom[x],
                                                             key="user_select_custom")
                    else:
                        st.warning("No users available")
                        selected_user_id_custom = None
                
                custom_description = st.text_area("Task Description", key="custom_description")
                custom_requirements = st.text_area("Requirements (one per line)", key="custom_requirements")
                assignment_note_custom = st.text_area("Assignment Note (optional)", 
                                                    placeholder="Add any specific instructions for this user...",
                                                    key="note_custom")
                
                # Submit button
                submit_custom = st.form_submit_button("Create & Assign Custom Task", use_container_width=True)
                
                if submit_custom:
                    if custom_title and custom_description and selected_user_id_custom:
                        # Create the custom task first
                        req_list = [req.strip() for req in custom_requirements.split('\n') if req.strip()]
                        
                        custom_task_data = {
                            "title": custom_title,
                            "description": custom_description,
                            "due_date": datetime.combine(custom_due_date, datetime.min.time()).replace(tzinfo=timezone.utc),
                            "points": custom_points,
                            "is_active": True,
                            "team_id": None,
                            "type": "individual",
                            "difficulty": custom_difficulty,
                            "track": custom_track,
                            "requirements": req_list,
                            "created_by": st.session_state.admin_username,
                            "created_at": datetime.now(timezone.utc),
                            "updated_at": datetime.now(timezone.utc),
                            "is_custom": True,  # Mark as custom task
                            "assigned_to": ObjectId(selected_user_id_custom)  # Link to specific user
                        }
                        
                        # Insert the custom task
                        custom_task_result = tasks_col.insert_one(custom_task_data)
                        custom_task_id = custom_task_result.inserted_id
                        
                        # Create assignment record
                        assignment_data = {
                            "task_id": custom_task_id,
                            "user_id": ObjectId(selected_user_id_custom),
                            "assigned_by": st.session_state.admin_username,
                            "assigned_at": datetime.now(timezone.utc),
                            "note": assignment_note_custom,
                            "status": "assigned",
                            "assignment_type": "custom"
                        }
                        
                        db.task_assignments.insert_one(assignment_data)
                        
                        # Success message
                        user_name = user_options_custom[selected_user_id_custom]
                        st.success(f"Custom task '{custom_title}' created and assigned to {user_name} successfully!")
                        st.rerun()
                    else:
                        st.error("Please fill in all required fields and select a user!")
    
    st.markdown("---")
    
    # Show recent task assignments
    with st.expander("📋 Recent Task Assignments"):
        recent_assignments = list(db.task_assignments.find({}).sort("assigned_at", -1).limit(10))
        
        if recent_assignments:
            for assignment in recent_assignments:
                task = tasks_col.find_one({"_id": assignment["task_id"]})
                user = users_col.find_one({"_id": assignment["user_id"]})
                
                if task and user:
                    col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
                    
                    with col1:
                        st.write(f"**Task:** {task['title']}")
                        if task.get('is_custom'):
                            st.write("🔖 *Custom Task*")
                    with col2:
                        st.write(f"**Assigned to:** {user['name']}")
                    with col3:
                        assignment_type = assignment.get('assignment_type', 'existing')
                        st.write(f"**Type:** {assignment_type.title()}")
                    with col4:
                        if st.button("Remove", key=f"remove_assignment_{assignment['_id']}"):
                            db.task_assignments.delete_one({"_id": assignment["_id"]})
                            # If it's a custom task, optionally remove the task too
                            if task.get('is_custom'):
                                if st.button("Also delete custom task?", key=f"delete_custom_{task['_id']}"):
                                    tasks_col.delete_one({"_id": task["_id"]})
                            st.success("Assignment removed!")
                            st.rerun()
                    
                    if assignment.get("note"):
                        st.write(f"*Note: {assignment['note']}*")
                    
                    assigned_date = assignment.get('assigned_at', 'Unknown')
                    if hasattr(assigned_date, 'strftime'):
                        assigned_str = assigned_date.strftime('%Y-%m-%d %H:%M')
                    else:
                        assigned_str = str(assigned_date)
                    st.write(f"*Assigned on: {assigned_str}*")
                    st.markdown("---")
        else:
            st.info("No task assignments yet.")
    
    st.markdown("---")
    
    # Task list
    st.subheader("All Tasks")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        track_filter = st.selectbox("Filter by Track", ["All"] + list(TRACKS.keys()), 
                                  format_func=lambda x: TRACKS[x] if x in TRACKS else x, 
                                  key="task_track_filter")
    with col2:
        difficulty_filter = st.selectbox("Filter by Difficulty", ["All", "beginner", "intermediate", "advanced"])
    with col3:
        status_filter = st.selectbox("Filter by Status", ["All", "Active", "Inactive"], key="task_status_filter")
    
    # Build query
    query = {}
    if track_filter != "All":
        query["track"] = track_filter
    if difficulty_filter != "All":
        query["difficulty"] = difficulty_filter
    if status_filter == "Active":
        query["is_active"] = True
    elif status_filter == "Inactive":
        query["is_active"] = False
    
    tasks = list(tasks_col.find(query).sort("created_at", -1))
    
    if tasks:
        for task in tasks:
            # Safe track lookup
            track_name = TRACKS.get(task.get('track', ''), task.get('track', 'Unknown'))
            
            with st.expander(f"{task['title']} - {track_name} ({task['difficulty']})"):
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.write(f"**Description:** {task['description']}")
                    st.write(f"**Points:** {task['points']}")
                    
                    # Safe date handling
                    due_date = task.get('due_date', 'Not set')
                    if hasattr(due_date, 'strftime'):
                        due_date_str = due_date.strftime('%Y-%m-%d')
                    elif isinstance(due_date, str):
                        due_date_str = due_date
                    else:
                        due_date_str = str(due_date)
                    st.write(f"**Due Date:** {due_date_str}")
                    
                    st.write(f"**Type:** {task['type']}")
                    if task.get('requirements'):
                        st.write("**Requirements:**")
                        for req in task['requirements']:
                            st.write(f"• {req}")
                
                with col2:
                    st.write(f"**Status:** {'✅ Active' if task['is_active'] else '❌ Inactive'}")
                    
                    # Toggle active status
                    if st.button(f"{'Deactivate' if task['is_active'] else 'Activate'}", key=f"toggle_{task['_id']}"):
                        tasks_col.update_one(
                            {"_id": task["_id"]},
                            {"$set": {"is_active": not task['is_active'], "updated_at": datetime.now(timezone.utc)}}
                        )
                        st.rerun()
    else:
        st.info("No tasks found matching the criteria.")

def submissions_management():
    st.header("📄 Submissions Management")
    
    # Submission statistics
    total_subs = submissions_col.count_documents({})
    approved_subs = submissions_col.count_documents({"status": "approved"})
    pending_subs = submissions_col.count_documents({"status": "pending"})
    rejected_subs = submissions_col.count_documents({"status": "rejected"})
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total", total_subs)
    with col2:
        st.metric("Approved", approved_subs)
    with col3:
        st.metric("Pending", pending_subs)
    with col4:
        st.metric("Rejected", rejected_subs)
    
    st.markdown("---")
    
    # Submissions list
    st.subheader("All Submissions")
    
    # Filters
    col1, col2 = st.columns(2)
    with col1:
        status_filter = st.selectbox("Filter by Status", ["All", "pending", "approved", "rejected"])
    with col2:
        sort_by = st.selectbox("Sort by", ["Newest", "Oldest"])
    
    # Build query
    query = {}
    if status_filter != "All":
        query["status"] = status_filter
    
    sort_order = -1 if sort_by == "Newest" else 1
    submissions = list(submissions_col.find(query).sort("submitted_at", sort_order))
    
    if submissions:
        for sub in submissions:
            user = users_col.find_one({"_id": sub["user_id"]})
            task = tasks_col.find_one({"_id": sub["task_id"]})
            
            with st.expander(f"{user['name'] if user else 'Unknown User'} - {task['title'] if task else 'Unknown Task'} - {sub['status'].upper()}"):
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.write(f"**User:** {user['name'] if user else 'Unknown'}")
                    st.write(f"**Task:** {task['title'] if task else 'Unknown'}")
                    st.write(f"**Submission URL:** {sub.get('submission_url', 'N/A')}")
                    st.write(f"**Submission Text:** {sub.get('submission_text', 'N/A')}")
                    # Safe date handling  
                    submitted_date = sub.get('submitted_at', 'Unknown')
                    if hasattr(submitted_date, 'strftime'):
                        submitted_str = submitted_date.strftime('%Y-%m-%d %H:%M')
                    else:
                        submitted_str = str(submitted_date)
                    st.write(f"**Submitted:** {submitted_str}")
                    st.write(f"**Current Points:** {sub.get('points', 0)}")
                
                with col2:
                    st.write(f"**Status:** {sub['status'].upper()}")
                    
                    # Status update form
                    new_status = st.selectbox("Update Status", ["pending", "approved", "rejected"], 
                                            index=["pending", "approved", "rejected"].index(sub["status"]),
                                            key=f"status_{sub['_id']}")
                    
                    if sub["status"] != "approved":
                        new_points = st.number_input("Award Points", min_value=0, value=int(sub.get('points', 0)), key=f"points_{sub['_id']}")
                    else:
                        new_points = int(sub.get('points', 0))
                    
                    if st.button("Update", key=f"update_{sub['_id']}"):
                        update_data = {
                            "status": new_status,
                            "points": str(new_points),
                            "updated_at": datetime.now(timezone.utc)
                        }
                        
                        submissions_col.update_one({"_id": sub["_id"]}, {"$set": update_data})
                        
                        # Update user stats if approved
                        if new_status == "approved" and sub["status"] != "approved":
                            users_col.update_one(
                                {"_id": sub["user_id"]},
                                {
                                    "$inc": {
                                        "stats.points": new_points,
                                        "stats.tasks_completed": 1
                                    }
                                }
                            )
                        
                        st.success("Submission updated!")
                        st.rerun()
    else:
        st.info("No submissions found matching the criteria.")

def forums_management():
    st.header("💬 Forums Management")
    
    # Create forum form
    with st.expander("➕ Create New Forum"):
        with st.form("create_forum"):
            col1, col2 = st.columns(2)
            
            with col1:
                title = st.text_input("Forum Title")
                creator_name = st.text_input("Creator Name", value="Admin")
            
            with col2:
                creator_email = st.text_input("Creator Email", value="admin@innoverse.com")
            
            description = st.text_area("Description")
            
            if st.form_submit_button("Create Forum"):
                if title and description:
                    forum_data = {
                        "_id": str(ObjectId()),
                        "title": title,
                        "description": description,
                        "team_id": None,
                        "creator": {
                            "name": creator_name,
                            "email": creator_email
                        },
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                    
                    forums_col.insert_one(forum_data)
                    st.success("Forum created successfully!")
                    st.rerun()
                else:
                    st.error("Title and description are required!")
    
    st.markdown("---")
    
    # Forums list
    st.subheader("All Forums")
    
    forums = list(forums_col.find({}).sort("created_at", -1))
    
    if forums:
        for forum in forums:
            # Get comment count
            comment_count = forum_comments_col.count_documents({"forum_id": forum["_id"]})
            
            with st.expander(f"{forum['title']} ({comment_count} comments)"):
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.write(f"**Description:** {forum['description']}")
                    
                    # Safe creator info handling
                    creator = forum.get('creator', {})
                    creator_name = creator.get('name', 'Unknown')
                    creator_email = creator.get('email', 'Unknown')
                    st.write(f"**Creator:** {creator_name} ({creator_email})")
                    
                    # Safe date handling
                    created_at = forum.get('created_at', 'Unknown')
                    if hasattr(created_at, 'strftime'):
                        created_str = created_at.strftime('%Y-%m-%d %H:%M')
                    else:
                        created_str = str(created_at)
                    st.write(f"**Created:** {created_str}")
                
                with col2:
                    if st.button(f"Delete Forum", key=f"delete_forum_{forum['_id']}"):
                        # Delete forum and its comments
                        forums_col.delete_one({"_id": forum["_id"]})
                        forum_comments_col.delete_many({"forum_id": forum["_id"]})
                        st.success("Forum deleted!")
                        st.rerun()
                
                # Show recent comments
                if comment_count > 0:
                    st.write("**Recent Comments:**")
                    recent_comments = list(forum_comments_col.find({"forum_id": forum["_id"]}).sort("created_at", -1).limit(3))
                    for comment in recent_comments:
                        user_name = comment.get("user", {}).get("full_name", "Unknown User")
                        st.write(f"• {user_name}: {comment['content'][:100]}...")
    else:
        st.info("No forums found.")

def analytics_page():
    st.header("📈 Analytics")
    
    # User registration over time
    st.subheader("User Registration Trend")
    users = list(users_col.find({}, {"created_at": 1, "profile.coding_track": 1}))
    
    if users:
        user_dates = []
        user_tracks = []
        
        for user in users:
            if "created_at" in user:
                user_dates.append(user["created_at"].date())
                user_tracks.append(TRACKS.get(user.get("profile", {}).get("coding_track", ""), "Unknown"))
        
        df = pd.DataFrame({"date": user_dates, "track": user_tracks})
        df["count"] = 1
        
        # Daily registrations
        daily_reg = df.groupby("date").count()["count"].reset_index()
        fig = px.line(daily_reg, x="date", y="count", title="Daily User Registrations")
        st.plotly_chart(fig, use_container_width=True)
        
        # Registrations by track
        track_reg = df.groupby("track").count()["count"].reset_index()
        fig = px.bar(track_reg, x="track", y="count", title="Registrations by Track")
        st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    
    # Task completion analytics
    st.subheader("Task Performance")
    
    # Get submission data
    submissions = list(submissions_col.find({}))
    tasks = list(tasks_col.find({}))
    
    if submissions and tasks:
        # Task completion rates
        task_stats = {}
        for task in tasks:
            task_submissions = [s for s in submissions if s["task_id"] == task["_id"]]
            approved_count = len([s for s in task_submissions if s["status"] == "approved"])
            total_count = len(task_submissions)
            
            task_stats[task["title"]] = {
                "total_submissions": total_count,
                "approved_submissions": approved_count,
                "completion_rate": (approved_count / total_count * 100) if total_count > 0 else 0
            }
        
        # Display top performing tasks
        if task_stats:
            df = pd.DataFrame.from_dict(task_stats, orient="index").reset_index()
            df.columns = ["Task", "Total Submissions", "Approved Submissions", "Completion Rate"]
            df = df.sort_values("Completion Rate", ascending=False)
            
            fig = px.bar(df.head(10), x="Task", y="Completion Rate", title="Top 10 Tasks by Completion Rate")
            fig.update_layout(xaxis_tickangle=45)
            st.plotly_chart(fig, use_container_width=True)
            
            st.dataframe(df, use_container_width=True)
    
    st.markdown("---")
    
    # Points distribution
    st.subheader("Points Distribution")
    users_with_points = list(users_col.find({}, {"name": 1, "stats.points": 1, "profile.coding_track": 1}))
    
    if users_with_points:
        points_data = []
        for user in users_with_points:
            points = user.get("stats", {}).get("points", 0)
            track = TRACKS.get(user.get("profile", {}).get("coding_track", ""), "Unknown")
            points_data.append({"user": user["name"], "points": points, "track": track})
        
        df = pd.DataFrame(points_data)
        
        # Points histogram
        fig = px.histogram(df, x="points", nbins=20, title="Points Distribution")
        st.plotly_chart(fig, use_container_width=True)
        
        # Top scorers by track
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Top 10 Overall")
            top_overall = df.nlargest(10, "points")[["user", "points"]]
            st.dataframe(top_overall, use_container_width=True)
        
        with col2:
            st.subheader("Average Points by Track")
            track_avg = df.groupby("track")["points"].mean().reset_index()
            fig = px.bar(track_avg, x="track", y="points", title="Average Points by Track")
            st.plotly_chart(fig, use_container_width=True)

if __name__ == "__main__":
    main()