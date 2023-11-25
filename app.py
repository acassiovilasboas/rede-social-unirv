from flask import Flask, jsonify, request
from py2neo import Graph
from py2neo import Node
from py2neo import NodeMatcher, Relationship

app = Flask(__name__)

graph = Graph("bolt://localhost:7687", auth=("neo4j", "toor"))

@app.route('/')
def index():
    return jsonify(message="REST API de banco nao relacional com banco neo4j"), 200


# LIST USERS
@app.route('/users', methods=['GET'])
def list_users():
    matcher = NodeMatcher(graph)
    users = matcher.match("User")
    all_users = [
        {
            'id': user.identity,
            "name": user["name"], 
            "age": user["age"], 
            "location": user["location"]
        } for user in users
    ]
    return jsonify(all_users), 200


# LIST FRIENDS BY USER
@app.route('/users/<int:user_id>/friends', methods=['GET'])
def list_friends(user_id):
    user_query = "MATCH (user:User) WHERE id(user) = $user_id RETURN user"
    user_result = graph.evaluate(user_query, user_id=user_id)
    
    if not user_result:
        return jsonify({"error": "Usuario não encontrado"}), 404

    user_profile = {
        'id': user_result.identity,
        'name': user_result['name'],
        'age': user_result['age'],
        'location': user_result['location']
    }
    
    friends_query = """
    MATCH (user:User)-[:FRIEND]->(friend:User)
    WHERE id(user) = $user_id
    RETURN collect(friend) AS friends
    """
    friends_result = graph.run(friends_query, user_id=user_id).data()

    friends_list = []
    if friends_result:
        friends_list = [
            {
                'id': friend.identity, 
                'name': friend['name'], 
                'age': friend['age'], 
                'location': friend['location']
            } for friend in friends_result[0]['friends']]

    response = {
        'profile': user_profile,
        'friends': friends_list
    }
    
    return jsonify(response), 200


# CREATE USER
@app.route('/users', methods=['POST'])
def create_user():
    data = request.get_json()
    user = Node("User", name=data['name'], age=data['age'], location=data['location'])
    graph.create(user)
    return jsonify({"message": "Usuario criado com sucesso"}), 201


# ADD FRIEND
@app.route('/users/<int:user_id>/friends', methods=['POST'])
def add_friend(user_id):
    try:
        data = request.get_json()
        friend_id = data['friend_id']

        matcher = NodeMatcher(graph)
        user = matcher.get(user_id)
        friend = matcher.get(friend_id)

        if user and friend:
            if not graph.match_one((user, friend), "FRIEND") and not graph.match_one((friend, user), "FRIEND"):
                # aresta usuario -> amigo
                relationship_user_to_friend = Relationship(user, "FRIEND", friend)
                graph.create(relationship_user_to_friend)
                
                # aresta amigo -> usuario
                relationship_friend_to_user = Relationship(friend, "FRIEND", user)
                graph.create(relationship_friend_to_user)

                return jsonify({"message": "Amizade adicionada"}), 201
            else:
                return jsonify({"message": "A amizade ja existe"}), 409
        else:
            return jsonify({"message": "Usuário não encontrado"}), 404
    except ValueError:
        return jsonify({"error": "ID invalido."}), 400


# REMOVE FRIEND
@app.route('/users/<int:user_id>/friends/<int:friend_id>', methods=['DELETE'])
def remove_friend(user_id, friend_id):
    try:
        tx = graph.begin()

        user = graph.nodes.get(user_id)
        friend = graph.nodes.get(friend_id)

        if user and friend:
            friendships = list(graph.match(nodes=[user, friend], r_type="FRIEND"))
            friendships.extend(list(graph.match(nodes=[friend, user], r_type="FRIEND")))

            if not friendships:
                return jsonify({"message": "A relação não existe"}), 404

            for friendship in friendships:
                tx.separate(friendship)

            tx.commit()
            return jsonify({"message": "Amizade removida"}), 200
        else:
            return jsonify({"error": "Usuario ou amigo não encontrado"}), 404

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        tx.rollback()
        return jsonify({"error": "Erro ao processar a solicitação"}), 500



if __name__ == '__main__':
    app.run(debug=True)
