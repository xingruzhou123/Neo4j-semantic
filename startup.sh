# docker run \
#   --restart always \
#   --publish=7474:7474 --publish=7687:7687 \
#   --volume="$(pwd)/data":/data \
#   --name neo4j \
#   neo4j

docker start neo4j
