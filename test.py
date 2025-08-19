import pymongo
from bson import ObjectId
from datetime import datetime

# MongoDB Configuration
MONGO_URI = "mongodb+srv://arkin:kansrarkin@cluster0.pzgo5g9.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

def test_mongodb_connection():
    """Test MongoDB connection and explore database structure"""
    try:
        print("🔌 Connecting to MongoDB...")
        client = pymongo.MongoClient(MONGO_URI)
        
        # Test connection
        client.admin.command('ping')
        print("✅ MongoDB connection successful!")
        
        # List all databases
        print("\n📊 Available databases:")
        for db_name in client.list_database_names():
            print(f"  - {db_name}")
        
        # Check each database for collections
        for db_name in client.list_database_names():
            if db_name not in ['admin', 'local', 'config']:  # Skip system databases
                print(f"\n📁 Collections in '{db_name}' database:")
                db = client[db_name]
                collections = db.list_collection_names()
                
                if not collections:
                    print("  - No collections found")
                else:
                    for collection_name in collections:
                        count = db[collection_name].count_documents({})
                        print(f"  - {collection_name}: {count} documents")
                        
                        # Show sample documents for small collections
                        if count > 0 and count <= 5:
                            print(f"    Sample documents:")
                            for doc in db[collection_name].find().limit(3):
                                print(f"      {doc}")
        
        return client
        
    except Exception as e:
        print(f"❌ Error connecting to MongoDB: {e}")
        return None

def check_specific_collections(client, db_name="test"):
    """Check specific collections we need"""
    print(f"\n🔍 Checking specific collections in '{db_name}' database...")
    
    db = client[db_name]
    required_collections = ['admins', 'users', 'tasks', 'notifications']
    
    for collection_name in required_collections:
        try:
            count = db[collection_name].count_documents({})
            print(f"📄 {collection_name}: {count} documents")
            
            if count > 0:
                print("  Sample documents:")
                for doc in db[collection_name].find().limit(2):
                    print(f"    {doc}")
            else:
                print("  Collection is empty")
                
        except Exception as e:
            print(f"  ❌ Error accessing {collection_name}: {e}")

def insert_test_admin(client, db_name="test"):
    """Insert test admin data"""
    print(f"\n➕ Inserting test admin into '{db_name}' database...")
    
    try:
        db = client[db_name]
        
        # Check if admin already exists
        existing_admin = db.admins.find_one({"username": "admin2"})
        if existing_admin:
            print("⚠️  Admin 'admin2' already exists!")
            print(f"   Existing admin: {existing_admin}")
            return
        
        # Insert new admin
        admin_doc = {
            "_id": ObjectId("68a09d9a6fd3f2d62e9da2c1"),
            "username": "admin2",
            "password": "mypassword123"
        }
        
        result = db.admins.insert_one(admin_doc)
        print(f"✅ Admin inserted successfully! ID: {result.inserted_id}")
        
        # Verify insertion
        inserted_admin = db.admins.find_one({"username": "admin2"})
        print(f"✅ Verification - Admin found: {inserted_admin}")
        
    except Exception as e:
        print(f"❌ Error inserting admin: {e}")

def insert_sample_data(client, db_name="test"):
    """Insert sample data for testing"""
    print(f"\n📋 Inserting sample data into '{db_name}' database...")
    
    try:
        db = client[db_name]
        
        # Sample user
        sample_user = {
            "_id": ObjectId("68a015e58e383c5c71149f49"),
            "google_id": "117411753688507398637",
            "email": "yash.48725095@gmail.com",
            "name": "YASH MISHRA",
            "picture": "https://lh3.googleusercontent.com/a/ACg8ocI2_kCUZKTYbqBAaacPRU_DyrbHBpXMHkthp9y7Kr575LKj4T6o=s96-c",
            "verified_email": True,
            "email_domain": "gmail.com",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "last_login": datetime.now(),
            "login_count": 6,
            "is_active": True,
            "profile": {
                "bio": "",
                "college": "",
                "course": "",
                "year": "3rd",
                "interests": [],
                "coding_track": "web dev"
            },
            "preferences": {
                "notifications": True,
                "privacy": "public"
            }
        }
        
        # Check if user exists
        if not db.users.find_one({"email": "yash.48725095@gmail.com"}):
            db.users.insert_one(sample_user)
            print("✅ Sample user inserted")
        else:
            print("⚠️  Sample user already exists")
        
        # Sample task template
        sample_task_template = {
            "task": "Make a Todo List",
            "track": "web dev",
            "points": 100,
            "description": "Create a functional todo list application"
        }
        
        if not db.task_templates.find_one({"task": "Make a Todo List"}):
            db.task_templates.insert_one(sample_task_template)
            print("✅ Sample task template inserted")
        else:
            print("⚠️  Sample task template already exists")
            
    except Exception as e:
        print(f"❌ Error inserting sample data: {e}")

def main():
    """Main function to run all tests"""
    print("🚀 MongoDB Database Test Script")
    print("=" * 50)
    
    # Test connection and explore database
    client = test_mongodb_connection()
    if not client:
        return
    
    # Check which database to use
    db_names = client.list_database_names()
    print(f"\n🎯 Available databases: {db_names}")
    
    # Try different common database names
    possible_db_names = ['test', 'admin', 'your_app_name', 'cluster0']
    
    for db_name in possible_db_names:
        if db_name in db_names or db_name == 'test':  # 'test' might not show up if empty
            print(f"\n🔍 Testing database: '{db_name}'")
            check_specific_collections(client, db_name)
            
            # Ask user if they want to insert test data
            response = input(f"\n❓ Insert test admin into '{db_name}' database? (y/n): ").lower()
            if response == 'y':
                insert_test_admin(client, db_name)
                
                # Ask for sample data
                response2 = input("❓ Insert sample user and task data? (y/n): ").lower()
                if response2 == 'y':
                    insert_sample_data(client, db_name)
                
                break
    
    print("\n✨ Test completed!")
    print("\n📝 Next steps:")
    print("1. Update your Streamlit app's database name if needed")
    print("2. Run the Streamlit app again")
    print("3. Try logging in with username: admin2, password: mypassword123")

if __name__ == "__main__":
    main()