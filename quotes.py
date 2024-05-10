from flask import Flask, render_template, request, redirect, make_response
from mongita import MongitaClientDisk
from bson import ObjectId
from passwords import hash_password, check_password
import datetime


app = Flask(__name__)

# Open a mongita client connection
client = MongitaClientDisk()

# Open a quote database
quotes_db = client.quotes_db
session_db = client.session_db
user_db = client.user_db
comments_db = client.comments_db
comments_collection = comments_db['comments']

import uuid


@app.route("/", methods=["GET"])
@app.route("/quotes", methods=["GET"])
def get_quotes():
    session_id = request.cookies.get("session_id", None)
    if not session_id:
        return redirect("/login")
    
    session_collection = session_db.session_collection
    session_data = session_collection.find_one({"session_id": session_id})
    if not session_data:
        return redirect("/logout")
    
    user = session_data.get("user", "unknown user")
    quotes_collection = quotes_db.quotes_collection
    user_quotes = list(quotes_collection.find({"owner": user}))
    public_quotes = list(quotes_collection.find({"public": True}))
    data = user_quotes + public_quotes
    
    # Convert ObjectId to string for serialization
    for item in data:
        item["_id"] = str(item["_id"])
        item["object"] = ObjectId(item["_id"])
    
    html = render_template("quotes.html", data=data, user=user)
    response = make_response(html)
    response.set_cookie("session_id", session_id)
    return response


@app.route("/search", methods=["GET"])
def search_quotes():
    session_id = request.cookies.get("session_id", None)
    if not session_id:
        return redirect("/login")

    search_query = request.args.get("q", "").strip()
    search_scope = request.args.get("scope", "all")

    session_collection = session_db.session_collection
    session_data = session_collection.find_one({"session_id": session_id})
    if not session_data:
        return redirect("/logout")

    user = session_data.get("user", "unknown user")

    quotes_collection = quotes_db.quotes_collection

    if search_scope == "user_quotes":
        data = list(quotes_collection.find({"owner": user}))
    elif search_scope == "public_quotes":
        data = list(quotes_collection.find({"public": True}))
    else:
        data = list(quotes_collection.find())

    if search_query:
        search_result = [quote for quote in data if search_query.lower() in quote.get("text", "").lower()]
        data = search_result

    for item in data:
        item["_id"] = str(item["_id"])
        item["object"] = ObjectId(item["_id"])

    return render_template("quotes.html", data=data, user=user, search_query=search_query, search_scope=search_scope)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        session_id = request.cookies.get("session_id")
        if session_id:
            return redirect("/quotes")
        return render_template("login.html")
    elif request.method == "POST":
        user = request.form.get("user", "")
        password = request.form.get("password", "")
        user_collection = user_db.user_collection
        user_data = user_collection.find_one({"user": user})
        if not user_data or not check_password(password, user_data.get("hashed_password", ""), user_data.get("salt", "")):
            response = redirect("/login")
            response.delete_cookie("session_id")
            return response
        session_id = str(uuid.uuid4())
        session_collection = session_db.session_collection
        session_collection.delete_one({"session_id": session_id})
        session_data = {"session_id": session_id, "user": user}
        session_collection.insert_one(session_data)
        response = redirect("/quotes")
        response.set_cookie("session_id", session_id)
        return response


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        session_id = request.cookies.get("session_id")
        if session_id:
            return redirect("/quotes")
        return render_template("register.html")
    elif request.method == "POST":
        user = request.form.get("user", "")
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        if password != password2:
            response = redirect("/register")
            response.delete_cookie("session_id")
            return response
        user_collection = user_db.user_collection
        if user_collection.find_one({"user": user}):
            return redirect("/login")
        hashed_password, salt = hash_password(password)
        user_collection.insert_one({"user": user, "hashed_password": hashed_password, "salt": salt})
        return redirect("/login")


@app.route("/logout", methods=["GET"])
def logout():
    session_id = request.cookies.get("session_id")
    if session_id:
        session_collection = session_db.session_collection
        session_collection.delete_one({"session_id": session_id})
    response = redirect("/login")
    response.delete_cookie("session_id")
    return response


@app.route("/add", methods=["GET", "POST"])
def add_quote():
    session_id = request.cookies.get("session_id")
    if not session_id:
        return redirect("/login")
    
    session_collection = session_db.session_collection
    session_data = session_collection.find_one({"session_id": session_id})
    if not session_data:
        return redirect("/logout")
    
    user = session_data.get("user", "unknown user")

    if request.method == "GET":
        return render_template("add_quote.html")
    elif request.method == "POST":
        quote = request.form.get("quote", "")
        author = request.form.get("author", "")
        date = request.form.get("date", "")
        public = request.form.get("public", "") == "on"

        if quote and author:
            quotes_collection = quotes_db.quotes_collection
            quotes_collection.insert_one({"owner": user, "text": quote, "author": author, "date": date, "public": public})
        return redirect("/quotes")


@app.route("/edit/<id>", methods=["GET", "POST"])
def edit_quote(id=None):
    session_id = request.cookies.get("session_id")
    if not session_id:
        return redirect("/login")
    
    session_collection = session_db.session_collection
    session_data = session_collection.find_one({"session_id": session_id})
    if not session_data:
        return redirect("/logout")
    
    user = session_data.get("user", "unknown user")

    if request.method == "GET":
        if id:
            quotes_collection = quotes_db.quotes_collection
            data = quotes_collection.find_one({"_id": ObjectId(id)})
            data["id"] = str(data["_id"])
            return render_template("edit_quote.html", data=data)
        return redirect("/quotes")
    elif request.method == "POST":
        _id = request.form.get("_id")
        text = request.form.get("newQuote", "")
        author = request.form.get("newAuthor", "")
        if _id:
            quotes_collection = quotes_db.quotes_collection
            values = {"$set": {"text": text, "author": author}}
            quotes_collection.update_one({"_id": ObjectId(_id)}, values)
        return redirect("/quotes")


@app.route("/delete/<id>", methods=["GET"])
def delete_quote(id=None):
    session_id = request.cookies.get("session_id")
    if not session_id:
        return redirect("/login")
    
    session_collection = session_db.session_collection
    session_data = session_collection.find_one({"session_id": session_id})
    if not session_data:
        return redirect("/logout")
    
    if id:
        quotes_collection = quotes_db.quotes_collection
        quotes_collection.delete_one({"_id": ObjectId(id)})
    return redirect("/quotes")

@app.route("/add_comment/<quote_id>", methods=["GET", "POST"])
def add_comment(quote_id):
    if request.method == 'POST':
        # Handle the POST request to add a comment
        comment_text = request.form.get('text')
        author = request.form.get('author')
        date = request.form.get('date')
        is_public = 'public' in request.form
        is_private = 'private' in request.form

         # Retrieve the ObjectId of the quote from the URL parameter
        quote_object_id = ObjectId(quote_id)

        # Add logic to add the comment to the quote document
        quotes_collection = quotes_db.quotes_collection
        quotes_collection.update_one({"_id": quote_object_id}, 
                                      {"$push": {"comments": {"text": comment_text, 
                                                              "author": author, 
                                                              "date": date, 
                                                              "public": is_public}}})
        return redirect('/quotes')  # Redirect to the home page after adding the comment
    elif request.method == 'GET':
        # Get the current date and time
        current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Render the add comment form
        return render_template("add_comment.html", quote_id=quote_id, current_date=current_date)
    else:
        return "Method Not Allowed", 405  # Handle other HTTP methods

if __name__ == '__main__':
    app.run(debug=True)




@app.route('/edit_comment/<quote_id>/<comment_id>', methods=['POST'])
def edit_comment(quote_id, comment_id):
    if request.method == 'POST':
        new_text = request.form.get('new_text')

        quotes_db.quotes_collection.update_one({'_id': ObjectId(quote_id), 'comments._id': ObjectId(comment_id)},
                                               {'$set': {'comments.$.text': new_text}})
        return redirect('/quotes')
    else:
        return "Method Not Allowed", 405


@app.route('/delete_comment/<quote_id>/<comment_id>', methods=['POST'])
def delete_comment(quote_id, comment_id):
    if request.method == 'POST':
        quotes_db.quotes_collection.update_one({'_id': ObjectId(quote_id)},
                                               {'$pull': {'comments': {'_id': ObjectId(comment_id)}}})
        return redirect('/quotes')
    else:
        return "Method Not Allowed", 405


if __name__ == '__main__':
    app.run(debug=True)
