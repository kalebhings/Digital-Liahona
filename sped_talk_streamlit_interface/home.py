import streamlit as st
import pandas as pd # Added for potential future use, but using Markdown for lists now

# --- Page Configuration ---
st.set_page_config(
    page_title="Network Analysis with Knowledge Graphs & Neo4j",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- Main Title ---
st.title("📡 Visualizing Network Connections: A Knowledge Graph Approach with Neo4j")
st.caption("Demonstrating how graph databases help analyze network activity and identify anomalies.")

# --- Tabs for Different Sections ---
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🕸️ What are Knowledge Graphs?",
    "🚀 Meet Neo4j",
    "💻 Building Our Network Graph",
    "🔍 Querying for Insights & Anomalies",
    "🌐 Diverse Real-World Use Cases" # Updated Tab Title
])

# --- TAB 1: What are Knowledge Graphs? ---
with tab1:
    st.header("🕸️ What are Knowledge Graphs?")
    st.markdown("""
    Imagine a way to store and connect information not just in rows and columns like a traditional database,
    but more like how our brains work – by linking related concepts. That's the core idea behind a knowledge graph.

    **In a Network Context:**
    * **Nodes (Entities/Objects):** Represent network entities.
        * *Example:* A `User` node, a `Device` (like a laptop or phone), a `Server`, a `Location` (derived from an IP address).
    * **Relationships (Edges):** Define how these entities interact or are related.
        * *Example:* A `User` `[:LOGGED_IN_VIA]` a `Device`, a `Device` `[:CONNECTED_TO]` a `Server`, an access event `[:ACCESSED_FROM]` a `Location`.
    * **Properties:** Attributes that describe nodes and relationships.
        * *Example:* A `User` node can have `username: "alice_g"`, `department: "Engineering"`.
        * A `[:LOGGED_IN_VIA]` relationship can have `timestamp: datetime()`, `ip: "74.125.224.72"`.
    """)

    st.subheader("How do they differ from Relational Databases (SQL)?")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        **Relational Databases (SQL):**
        * Data is stored in tables (rows and columns).
        * Relationships are defined using foreign keys and JOIN tables.
        * Analyzing complex event sequences or multi-hop connections (e.g., user -> device -> server -> location -> another server) can require many complex JOINs.
        * Schema is typically rigid.
        """)
    with col2:
        st.markdown("""
        **Knowledge Graphs (e.g., Neo4j):**
        * Data is stored as nodes and relationships.
        * Relationships are first-class citizens, directly connecting nodes.
        * Querying complex relationships and paths is often more intuitive and performant, as it involves traversing the graph structure directly.
        * Schema can be more flexible and evolve easily to accommodate new data types or event details.
        """)
    st.info("For network analysis, graphs excel at modeling the intricate web of connections and interactions, making it easier to spot unusual patterns or trace attack paths that might be obscured in tabular data.")
    # Updated image and parameter
    st.image("https://sdmntprsouthcentralus.oaiusercontent.com/files/00000000-3690-61f7-bde5-093ee90d3a49/raw?se=2025-05-08T03%3A57%3A45Z&sp=r&sv=2024-08-04&sr=b&scid=bcc6c205-ebc7-5fa1-ab63-6576240ebe2b&skoid=0abefe37-d2bd-4fcb-bc88-32bccbef6f7d&sktid=a48cca56-e6da-484e-a814-9c849652bcb3&skt=2025-05-07T06%3A25%3A43Z&ske=2025-05-08T06%3A25%3A43Z&sks=b&skv=2024-08-04&sig=3Q%2BvbwcKmZj0r8c1glmTQCaahzgjQFqICZCcr6yzRMs%3D", # Example image, original was broken
             caption="Graph vs. Relational",
             width=900) # Updated from use_column_width


# --- TAB 2: Meet Neo4j ---
with tab2:
    st.header("🚀 Meet Neo4j: The Graph Database")
    st.markdown("""
    To build and manage these powerful graphs, we use specialized databases. One of the most popular is **Neo4j**.
    """)
    col_logo, col_text, col_example_graph = st.columns([1,2,2]) # Added a column for the example graph
    with col_logo:
        # Found a working Neo4j logo URL
        st.image("https://www.eleventhdimensionsolutions.com/wp-content/uploads/2023/04/Neo4j-2.jpg", width=150, caption="Neo4j Logo")
    with col_text:
        st.markdown("""
        * **Native Graph Database:** Designed from the ground up to store, manage, and query connected data efficiently.
        * **Cypher Query Language:** A declarative, SQL-inspired query language for graphs. It uses ASCII art-like patterns to describe what you want to find.
        * **Property Graph Model:** Supports nodes, relationships, and properties on both.
        * **Scalable and Performant:** Optimized for graph traversals, crucial for analyzing large and complex networks.
        """)
    with col_example_graph:
        st.image("https://tbgraph.wordpress.com/wp-content/uploads/2020/04/starwars.png",
                 caption="Example of a Graph: Nodes and Relationships (Star Wars Graph by TBGraph)",
                 use_container_width=True)


    st.subheader("Cypher: The Language of Graphs")
    st.markdown("""
    A simple Cypher pattern for network analysis might be:
    `(user:User)-[:LOGGED_IN_VIA {ip: '1.2.3.4'}]->(device:Device)-[:CONNECTED_TO]->(server:Server)`
    This means: "Find a 'User' who logged in via a 'Device' from IP '1.2.3.4', where that 'Device' connected to a 'Server'."
    """)
    st.code("""
// Basic Cypher Structure for network events
MATCH (u:User)-[r:LOGGED_IN_VIA]->(d:Device)
WHERE u.department = 'Engineering' AND r.timestamp > datetime() - duration({days: 1})
RETURN u.username, d.deviceId, r.ip;
    """, language="cypher")

# --- TAB 3: Building Our Network Graph ---
with tab3:
    st.header("💻 Building Our Network Graph")
    st.markdown("We'll create nodes for users, devices, servers, and locations, then connect them with interaction relationships.")

    st.subheader("1. Creating Constraints and Indexes")
    st.markdown("Ensures data integrity (e.g., unique usernames, device IDs) and speeds up queries.")
    st.code("""
CREATE CONSTRAINT IF NOT EXISTS FOR (u:User) REQUIRE u.username IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (d:Device) REQUIRE d.deviceId IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (s:Server) REQUIRE s.ipAddress IS UNIQUE;
// CREATE CONSTRAINT IF NOT EXISTS FOR (l:Location) REQUIRE l.ipRange IS UNIQUE; // Or city/country
    """, language="cypher")
    st.success("Conceptual Result: Constraints and indexes are set up in Neo4j.")

    st.subheader("2. Creating Entity Nodes")
    st.markdown("Nodes represent the core components of our network.")
    st.code("""
// Location Nodes
CREATE (:Location {city: 'New York', country: 'USA', ipRangePrefix: '74.125.224.'});
CREATE (:Location {city: 'Moscow', country: 'Russia', ipRangePrefix: '93.158.134.'});

// User Nodes
CREATE (:User {username: 'alice_g', name: 'Alice Green', department: 'Engineering'});
CREATE (:User {username: 'david_s', name: 'David Smith', department: 'Engineering', status: 'Active'});
CREATE (:User {username: 'eve_m', name: 'Eve Malware', department: 'External', status: 'Suspended'});


// Device Nodes
CREATE (:Device {deviceId: 'alice_laptop_01', type: 'Laptop', os: 'Windows 10'});
CREATE (:Device {deviceId: 'unknown_device_77', type: 'Unknown', os: 'Unknown'});

// Server Nodes
CREATE (:Server {serverName: 'WebApp01', ipAddress: '192.168.1.10', service: 'Customer Portal'});
CREATE (:Server {serverName: 'Database01', ipAddress: '192.168.1.20', service: 'Main Database'});
CREATE (:Server {serverName: 'AuthServer01', ipAddress: '192.168.1.5', service: 'Authentication'});
// ... and more entities from the sample data
    """, language="cypher")
    st.success("Conceptual Result: User, Device, Server, and Location nodes are created.")

    st.subheader("3. Creating Relationships (Interactions & Ownership)")
    st.markdown("""
    This is where we model how entities interact. `MATCH` finds existing nodes, and `CREATE` forms the connections.
    Relationships like `LOGGED_IN_VIA`, `CONNECTED_TO`, `ACCESSED_FROM`, and `OWNS_DEVICE` are created.
    Timestamps, IP addresses, and ports are often stored as properties on these relationships.
    """)
    st.code("""
// Alice (normal activity)
MATCH (u:User {username: 'alice_g'}), (d:Device {deviceId: 'alice_laptop_01'}) CREATE (u)-[:OWNS_DEVICE]->(d);
MATCH (u:User {username: 'alice_g'}), (d:Device {deviceId: 'alice_laptop_01'}), (s:Server {serverName: 'WebApp01'}), (l:Location {city: 'New York'})
  CREATE (u)-[:LOGGED_IN_VIA {timestamp: datetime(), ip: '74.125.224.72'}]->(d)-[:ACCESSED_FROM]->(l),
         (d)-[:CONNECTED_TO {port: 443, protocol: 'HTTPS', timestamp: datetime()}]->(s);

// David logs in from Moscow (potential anomaly)
MATCH (u:User {username: 'david_s'}), (d:Device {deviceId: 'david_laptop_01'}), (s:Server {serverName: 'Database01'}), (l:Location {city: 'Moscow'})
  CREATE (u)-[:LOGGED_IN_VIA {timestamp: datetime(), ip: '93.158.134.50', status: 'Successful'}]->(d)-[:ACCESSED_FROM]->(l),
         (d)-[:CONNECTED_TO {port: 5432, protocol: 'TCP', timestamp: datetime()}]->(s);

// Eve (suspended user) attempts login, then succeeds from unknown device & new location
MATCH (u:User {username: 'eve_m'}), (s:Server {serverName: 'AuthServer01'})
  CREATE (u)-[:LOGIN_ATTEMPT {timestamp: datetime({epochSeconds: timestamp()/1000 - 600}), ip: '74.125.224.100', status: 'Failed_SuspendedUser'}]->(s);
MATCH (u:User {username: 'eve_m'}), (d:Device {deviceId: 'unknown_device_77'}), (s:Server {serverName: 'WebApp01'}), (l:Location {city: 'Moscow'})
  CREATE (u)-[:LOGGED_IN_VIA {timestamp: datetime({epochSeconds: timestamp()/1000 - 300}), ip: '93.158.134.99', status: 'Successful_CompromiseSuspected'}]->(d)-[:ACCESSED_FROM]->(l),
         (d)-[:CONNECTED_TO {port: 80, protocol: 'HTTP', timestamp: datetime({epochSeconds: timestamp()/1000 - 300})}]->(s);
// ... and more relationships from the sample data
    """, language="cypher")
    st.success("Conceptual Result: Relationships are formed, modeling network activity.")
    st.markdown("---")
    st.markdown("**(In Neo4j Browser, this graph would visually show these connections and potential attack paths or policy violations!)**")

# --- TAB 4: Querying for Insights & Anomalies ---
with tab4:
    st.header("🔍 Querying for Insights & Anomalies")
    st.markdown("Let's ask some security-relevant questions using Cypher.")

    st.subheader("Query 1: Users logging in from unusual/flagged locations.")
    st.markdown("Identify users from specific departments logging in from unexpected geographic locations.")
    st.code("""
MATCH (u:User)-[r:LOGGED_IN_VIA]->(d:Device)-[:ACCESSED_FROM]->(l:Location)
WHERE l.city = 'Moscow' AND u.department <> 'External' // Example: Moscow is flagged for non-external staff
RETURN u.username, u.department, l.city, r.ip, r.timestamp
ORDER BY r.timestamp DESC;
    """, language="cypher")
    st.info("""
    **Conceptual Result for David Smith (Table View):**
    A table showing:
    - david_s | Engineering | Moscow | 93.158.134.50 | <timestamp>
    *(This highlights David, an Engineer, logging in from Moscow, which could be an anomaly.)*
    """)

    st.subheader("Query 2: Logins by suspended users.")
    st.markdown("Detect any network activity (login attempts or successes) by users who should be inactive.")
    st.code("""
MATCH (u:User {status: 'Suspended'})-[r:LOGGED_IN_VIA|LOGIN_ATTEMPT]->(target)
RETURN u.username, type(r) AS eventType, r.status AS eventStatus, r.ip, r.timestamp
ORDER BY r.timestamp DESC;
    """, language="cypher")
    st.info("""
    **Conceptual Result for Eve Malware (Table View):**
    A table showing:
    - eve_m | LOGIN_ATTEMPT | Failed_SuspendedUser | 74.125.224.100 | <timestamp_attempt>
    - eve_m | LOGGED_IN_VIA | Successful_CompromiseSuspected | 93.158.134.99 | <timestamp_success>
    *(Shows Eve's failed attempts and a later suspicious success.)*
    """)

    st.subheader("Query 3: Detect rapid geo-location jumps for a device.")
    st.markdown("Find if a single device appears to log in from geographically distant locations in an impossibly short time.")
    st.code("""
MATCH (u:User)-[r1:LOGGED_IN_VIA]->(d:Device)-[:ACCESSED_FROM]->(l1:Location)
WITH u, d, r1, l1
MATCH (u)-[r2:LOGGED_IN_VIA]->(d)-[:ACCESSED_FROM]->(l2:Location)
WHERE r1.timestamp > r2.timestamp
  AND duration.between(r2.timestamp, r1.timestamp).minutes < 60 // Within 60 mins
  AND l1.city <> l2.city // Different cities
RETURN u.username, d.deviceId,
       l1.city AS location1, r1.ip AS ip1, r1.timestamp AS time1,
       l2.city AS location2, r2.ip AS ip2, r2.timestamp AS time2
ORDER BY u.username, time1 DESC;
    """, language="cypher")
    st.info("""
    **Conceptual Result for Alice's Phone (Table View, if data supports it):**
    - alice_g | alice_phone_02 | San Francisco | 104.16.0.25 | <time_SF> | New York | 74.125.224.73 | <time_NY>
    *(Highlights Alice's phone logging in from SF very shortly after NY.)*
    """)

    st.subheader("Query 4: Devices used by multiple users.")
    st.markdown("Identify devices that have been used by more than one user account, which could indicate a shared workstation (normal) or a compromised device (abnormal).")
    st.code("""
MATCH (d:Device)<-[r:LOGGED_IN_VIA|OWNS_DEVICE]-(u:User)
WITH d, collect(DISTINCT u.username) AS usersWhoUsedDevice
WHERE size(usersWhoUsedDevice) > 1
RETURN d.deviceId, d.type, usersWhoUsedDevice;
    """, language="cypher")
    st.info("""
    **Conceptual Result (Table View, e.g., if 'unknown_device_77' was also used by David before Eve):**
    - unknown_device_77 | Unknown | ['david_s', 'eve_m']
    *(This would show the unknown device linked to multiple users, including the suspicious Eve.)*
    """)

    st.subheader("Query 5: Visualizing an Anomaly and Related Activity (Graph View)")
    st.markdown("""
    This query is designed for Neo4j Browser to visually display connections.
    It focuses on 'eve_m's suspicious login, the server she accessed, and other users who accessed the *same server*,
    potentially highlighting a broader scope of investigation.
    """)
    st.code("""
// Query for Visual Graph: Eve's Anomaly & Potentially Related Users/Activity

// Part 1: Identify Eve's suspicious login, the device used, the server accessed, and the location
MATCH p1 = (eve:User {username: 'eve_m'})
           -[r_eve:LOGGED_IN_VIA {status: 'Successful_CompromiseSuspected'}]->(d_eve:Device)
           -[c_eve:CONNECTED_TO]->(compromised_server:Server)
MATCH p2 = (d_eve)-[:ACCESSED_FROM]->(l_eve:Location) // Eve's login location

// Part 2: Identify other users who connected to the SAME compromised_server,
// their devices, login relationships, and connection details.
OPTIONAL MATCH p3 = (other_user:User)
                   -[r_other:LOGGED_IN_VIA]->(d_other:Device)
                   -[c_other:CONNECTED_TO]->(compromised_server)
WHERE other_user <> eve // Ensure we are looking at users other than Eve

// Part 3: For those other users, find their login locations
OPTIONAL MATCH p4 = (d_other)-[:ACCESSED_FROM]->(l_other:Location)
WHERE (p3 IS NOT NULL AND p4 IS NOT NULL) OR (p3 IS NULL AND p4 IS NULL)

// Part 4: (Bonus) Show devices Eve OWNS to give more context about her
OPTIONAL MATCH p5 = (eve)-[:OWNS_DEVICE]->(owned_by_eve_device:Device)

// Returning the paths (p1, p2, p3, p4, p5) will instruct Neo4j Browser
// to render all nodes and relationships within these paths.
RETURN p1, p2, p3, p4, p5
    """, language="cypher")
    st.image("graph.png")


# --- TAB 5: Diverse Real-World Use Cases ---
with tab5:
    st.header("🌐 Diverse Real-World Use Cases for Knowledge Graphs") # Updated Header
    st.markdown("""
    Knowledge graphs, powered by databases like Neo4j, are incredibly versatile and find applications across a multitude of domains beyond just cybersecurity. Their ability to model, connect, and query complex relationships provides significant value.
    """)

    st.subheader("General Applications:")
    st.markdown("""
    * **GraphRAG (Retrieval Augmented Generation):**
        * Enhancing Large Language Models (LLMs) by grounding them in factual knowledge from a graph. This improves accuracy, reduces hallucinations, and provides explainable AI by showing data sources and connections.
    * **Generative AI & Contextual Understanding:**
        * Providing LLMs with structured knowledge to understand context better, generate more relevant content, and perform complex reasoning tasks.
    * **Fraud Detection & Analytics:**
        * Uncovering sophisticated fraud rings and collusive behavior by analyzing networks of accounts, transactions, devices, and IP addresses in real-time.
        * Identifying subtle patterns that traditional systems might miss.
    * **Network & IT Operations (Cybersecurity & More):**
        * Mapping dependencies in IT infrastructure to predict outage impacts (as discussed).
        * Optimizing network performance and resource allocation.
        * Root cause analysis for IT incidents.
    * **Real-time Recommendation Engines:**
        * Powering personalized recommendations for products (e-commerce), content (media), connections (social networks), and more by understanding user preferences and item relationships.
    * **Data Management & Lineage:**
        * Creating a unified view of data from disparate sources (data fabrics, master data management).
        * Tracking data provenance and transformations for compliance and trust.
    """)

    st.subheader("Industry-Specific Use Cases:")
    col_fin_gov, col_health_retail_telco = st.columns(2)

    with col_fin_gov:
        st.markdown("""
        **Financial Services:**
        * **Anti-Money Laundering (AML):** Tracing illicit fund flows.
        * **Know Your Customer (KYC):** Understanding complex customer entity relationships.
        * **Risk Management:** Assessing interconnected financial risks.
        * **Algorithmic Trading:** Identifying market patterns and influences.

        **Government & Public Sector:**
        * **Intelligence Analysis:** Connecting disparate pieces of information to uncover threats or insights.
        * **Law Enforcement:** Investigating criminal networks.
        * **Public Resource Optimization:** Managing city services, infrastructure, and emergency response.
        * **Regulatory Compliance:** Ensuring adherence to complex legal frameworks.
        """)

    with col_health_retail_telco:
        st.markdown("""
        **Healthcare & Life Sciences:**
        * **Drug Discovery & Repurposing:** Identifying relationships between genes, proteins, diseases, and compounds.
        * **Personalized Medicine:** Tailoring treatments based on individual patient graphs (genomics, lifestyle, medical history).
        * **Clinical Trial Management:** Optimizing patient recruitment and tracking.
        * **Medical Knowledge Management:** Structuring and querying vast amounts of medical literature and research.

        **Retail & E-commerce:**
        * **Supply Chain Optimization:** Tracking goods from source to consumer, identifying bottlenecks.
        * **Customer 360:** Gaining a holistic view of customer interactions and preferences.
        * **Inventory Management:** Optimizing stock levels based on demand patterns and relationships.

        **Telecommunications:**
        * **Network Planning & Optimization:** Managing complex network infrastructure.
        * **Customer Service:** Resolving issues faster by understanding service dependencies.
        * **Churn Prediction:** Identifying at-risk customers based on usage patterns and social connections.
        """)

    st.info("""
    **The Core Advantage Across All Domains:** Knowledge graphs excel at making complex, interconnected data understandable and actionable, enabling deeper insights, better predictions, and more informed decisions.
    """)
    st.balloons()


st.sidebar.header("About this Demo")
st.sidebar.info(
    "This Streamlit application demonstrates how Knowledge Graphs and Neo4j can be used for "
    "network analysis and a variety of other applications. The Cypher queries shown are for illustrative purposes."
)

