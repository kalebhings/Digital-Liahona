# Step 1: Update System Packages
`sudo apt update && sudo apt upgrade -y`
# Step 2: Install Docker
## a. Install prerequisite packages
`sudo apt install apt-transport-https ca-certificates curl software-properties-common -y`
## b. Add Docker’s official GPG key
`curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg`
## c. Add Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
## d. Install Docker
sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io -y
# e. Start and enable Docker
sudo systemctl enable --now docker
# f. Optional: Run Docker as a non-root user
sudo usermod -aG docker $USER
newgrp docker
# Step 3: Install Docker Compose (optional but recommended)
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
  -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
docker-compose --version
# Step 4: Run Neo4j in Docker
## a. Create a directory to persist data
mkdir -p ~/neo4j/data
# b. Run Neo4j container
docker run \
  --name neo4j \
  -p7474:7474 -p7687:7687 \
  -d \
  -e NEO4J_AUTH=neo4j/password \
  -e NEO4J_PLUGINS='["apoc","graph-data-science"]' \
  -e NEO4J_dbms_security_procedures_unrestricted=apoc.* \
  -e NEO4J_dbms_security_procedures_allowlist=apoc.*,gds.* \
  -e NEO4J_apoc_import_file_enabled=true \
  -e NEO4J_apoc_import_file_use__neo4j__config=true \
  -v $HOME/neo4j/data:/data \
  neo4j:latest
# Step 5: Enter neo4j container
docker exec -it neo4j bash
# Step 6: Install vim inside the container
apt update && apt install vim -y
# Step 7: Edit conf file
## a. Open neo4j.conf in editor
vim /var/lib/neo4j/conf/neo4j.conf
## b. Make the following changes:
server.default_listen_address=.0.0.0
server.bolt.listen_address-0.0.0.0:7687
server.http.listen_address=0.0.0.0:7474
# Step 8: Exit the container and restart it
docker restart neo4j
