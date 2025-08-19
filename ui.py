import streamlit as st
import pymongo
from datetime import datetime
from bson import ObjectId
import pandas as pd

# MongoDB Configuration
MONGO_URI = "mongodb+srv://arkin:kansrarkin@cluster0.pzgo5g9.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

@st.cache_resource
def init_connection():
    """Initialize MongoDB connection"""
    try:
        client = pymongo.MongoClient(MONGO_URI)
        # Test the connection
        client.admin.command('ping')
        # Use the correct database name from your MongoDB cluster
        db = client['Cluster0']  # Your actual database name
        return db
    except Exception as e:
        st.error(f"Failed to connect to MongoDB: {e}")
        return None

def authenticate_admin(username, password, db):
    """Authenticate admin credentials"""
    try:
        admin = db.admins.find_one({"username": username, "password": password})
        return admin is not None, admin
    except Exception as e:
        st.error(f"Authentication error: {e}")
        return False, None

def get_users_by_track(track, db):
    """Get all users filtered by coding track"""
    try:
        users = list(db.users.find({"profile.coding_track": track}))
        return users
    except Exception as e:
        st.error(f"Error fetching users: {e}")
        return []

def get_all_tasks(db):
    """Get all available tasks"""
    try:
        # Assuming you have a tasks collection with predefined tasks
        # If not, you can create sample tasks or modify this function
        tasks = list(db.task_templates.find())  # Change collection name as needed
        if not tasks:
            # Sample tasks if collection is empty
            sample_tasks = [
                {"task": "Make a Todo List", "track": "web dev", "points": 100},
                {"task": "Build a Calculator", "track": "web dev", "points": 80},
                {"task": "Create ML Model", "track": "ai", "points": 150},
                {"task": "Build Mobile App", "track": "app dev", "points": 120},
                {"task": "Implement Binary Search", "track": "dsa", "points": 90}
            ]
            return sample_tasks
        return tasks
    except Exception as e:
        st.error(f"Error fetching tasks: {e}")
        return []

def assign_task_to_user(admin_id, admin_name, user_id, user_name, track, task, db):
    """Assign task to a user"""
    try:
        task_doc = {
            "assigned_by": ObjectId(admin_id),
            "assigned_by_name": admin_name,
            "assigned_to": ObjectId(user_id),
            "assigned_to_name": user_name,
            "coding_track": track,
            "task": task,
            "timestamp": datetime.now(),
            "status": "pending",
            "points": None
        }
        result = db.tasks.insert_one(task_doc)
        return result.inserted_id is not None
    except Exception as e:
        st.error(f"Error assigning task: {e}")
        return False

def get_submitted_tasks(track, db):
    """Get all submitted tasks for a track"""
    try:
        tasks = list(db.tasks.find({
            "coding_track": track,
            "status": "submitted"
        }))
        return tasks
    except Exception as e:
        st.error(f"Error fetching submitted tasks: {e}")
        return []

def update_task_points(task_id, points, db):
    """Update task with points and mark as completed"""
    try:
        result = db.tasks.update_one(
            {"_id": ObjectId(task_id)},
            {"$set": {"points": points, "status": "completed"}}
        )
        return result.modified_count > 0
    except Exception as e:
        st.error(f"Error updating task: {e}")
        return False

def post_notice(title, content, track, db):
    """Post a notice to the forum"""
    try:
        notice_doc = {
            "title": title,
            "content": content,
            "created_at": datetime.now(),
            "coding_track": track
        }
        # Use forum_posts collection as shown in your database
        result = db.forum_posts.insert_one(notice_doc)
        return result.inserted_id is not None
    except Exception as e:
        st.error(f"Error posting notice: {e}")
        return False

def main():
    st.set_page_config(page_title="Admin Dashboard", page_icon="👨‍💼", layout="wide")
    
    # Initialize database connection
    db = init_connection()
    if db is None:
        st.stop()
    
    # Initialize session state
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'admin_info' not in st.session_state:
        st.session_state.admin_info = None
    if 'selected_track' not in st.session_state:
        st.session_state.selected_track = None
    
    # Login Page
    if not st.session_state.logged_in:
        st.title("🔐 Admin Login")
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            with st.form("login_form"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Login", use_container_width=True)
                
                if submitted:
                    auth_result, admin_data = authenticate_admin(username, password, db)
                    if auth_result:
                        st.session_state.logged_in = True
                        st.session_state.admin_info = {
                            "username": username,
                            "admin_id": str(admin_data["_id"])
                        }
                        st.success("Login successful!")
                        st.rerun()
                    else:
                        st.error("Invalid credentials!")
        return
    
    # Main Dashboard
    st.title("👨‍💼 Admin Dashboard")
    st.write(f"Welcome, {st.session_state.admin_info['username']}!")
    
    # Logout button
    if st.button("Logout", type="secondary"):
        st.session_state.logged_in = False
        st.session_state.admin_info = None
        st.session_state.selected_track = None
        st.rerun()
    
    # Track Selection
    if st.session_state.selected_track is None:
        st.subheader("🎯 Select a Track")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.button("🌐 Web Dev", use_container_width=True):
                st.session_state.selected_track = "web dev"
                st.rerun()
        
        with col2:
            if st.button("🤖 AI", use_container_width=True):
                st.session_state.selected_track = "ai"
                st.rerun()
        
        with col3:
            if st.button("📱 App Dev", use_container_width=True):
                st.session_state.selected_track = "app dev"
                st.rerun()
        
        with col4:
            if st.button("📊 DSA", use_container_width=True):
                st.session_state.selected_track = "dsa"
                st.rerun()
        
        return
    
    # Main Menu for Selected Track
    st.subheader(f"📋 Managing: {st.session_state.selected_track.upper()}")
    
    if st.button("← Back to Track Selection"):
        st.session_state.selected_track = None
        st.rerun()
    
    # Main Actions
    tab1, tab2, tab3 = st.tabs(["📝 Assign Task", "✅ Check Submissions", "📢 Post Notice"])
    
    # Tab 1: Assign Task
    with tab1:
        st.subheader("Assign Task to Students")
        
        # Get users for selected track
        users = get_users_by_track(st.session_state.selected_track, db)
        
        if not users:
            st.warning(f"No users found for {st.session_state.selected_track} track.")
        else:
            # Display users
            st.write(f"Found {len(users)} students in {st.session_state.selected_track} track:")
            
            # Create user selection
            user_options = {}
            for user in users:
                user_id = str(user['_id'])
                user_name = user.get('name', 'Unknown')
                user_email = user.get('email', 'No email')
                user_options[f"{user_name} ({user_email})"] = user_id
            
            # Add "Select All" option
            user_options["🔄 Select All"] = "all"
            
            selected_users = st.multiselect(
                "Select students to assign task:",
                options=list(user_options.keys()),
                default=[]
            )
            
            if selected_users:
                # Get available tasks
                available_tasks = get_all_tasks(db)
                task_options = [task.get('task', 'Unnamed Task') for task in available_tasks 
                              if task.get('track') == st.session_state.selected_track or not task.get('track')]
                
                if not task_options:
                    task_name = st.text_input("Enter custom task name:")
                else:
                    task_choice = st.selectbox("Select a task:", ["Custom Task"] + task_options)
                    if task_choice == "Custom Task":
                        task_name = st.text_input("Enter custom task name:")
                    else:
                        task_name = task_choice
                
                if st.button("Assign Task", type="primary"):
                    if task_name:
                        success_count = 0
                        
                        # Handle "Select All" option
                        if "🔄 Select All" in selected_users:
                            target_users = users
                        else:
                            target_users = [user for user in users 
                                          if f"{user.get('name', 'Unknown')} ({user.get('email', 'No email')})" in selected_users]
                        
                        for user in target_users:
                            if assign_task_to_user(
                                admin_id=st.session_state.admin_info['admin_id'],
                                admin_name=st.session_state.admin_info['username'],
                                user_id=str(user['_id']),
                                user_name=user.get('name', 'Unknown'),
                                track=st.session_state.selected_track,
                                task=task_name,
                                db=db
                            ):
                                success_count += 1
                        
                        st.success(f"Task assigned to {success_count} students successfully!")
                    else:
                        st.error("Please enter a task name!")
    
    # Tab 2: Check Submissions
    with tab2:
        st.subheader("Check Submitted Tasks")
        
        submitted_tasks = get_submitted_tasks(st.session_state.selected_track, db)
        
        if not submitted_tasks:
            st.info("No submitted tasks found for this track.")
        else:
            st.write(f"Found {len(submitted_tasks)} submitted tasks:")
            
            for i, task in enumerate(submitted_tasks):
                with st.expander(f"Task: {task.get('task', 'Unknown')} - Student: {task.get('assigned_to_name', 'Unknown')}"):
                    col1, col2 = st.columns([2, 1])
                    
                    with col1:
                        st.write(f"**Student:** {task.get('assigned_to_name', 'Unknown')}")
                        st.write(f"**Task:** {task.get('task', 'Unknown')}")
                        st.write(f"**Submitted:** {task.get('timestamp', 'Unknown')}")
                        st.write(f"**Status:** {task.get('status', 'Unknown')}")
                    
                    with col2:
                        points = st.number_input(
                            "Award Points:",
                            min_value=0,
                            max_value=200,
                            value=100,
                            key=f"points_{i}"
                        )
                        
                        if st.button(f"Award Points", key=f"award_{i}"):
                            if update_task_points(str(task['_id']), points, db):
                                st.success("Points awarded successfully!")
                                st.rerun()
                            else:
                                st.error("Failed to award points!")
    
    # Tab 3: Post Notice
    with tab3:
        st.subheader("Post Notice to Forum")
        
        with st.form("notice_form"):
            notice_title = st.text_input("Notice Title:")
            notice_content = st.text_area("Notice Content:", height=150)
            
            submitted = st.form_submit_button("Post Notice", type="primary")
            
            if submitted:
                if notice_title and notice_content:
                    if post_notice(notice_title, notice_content, st.session_state.selected_track, db):
                        st.success("Notice posted successfully!")
                    else:
                        st.error("Failed to post notice!")
                else:
                    st.error("Please fill in both title and content!")

if __name__ == "__main__":
    main()