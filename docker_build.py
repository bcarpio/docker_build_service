import os, json, shutil
from bson import json_util, ObjectId
from flask import Flask, request
from flask_restful import Resource, Api, reqparse, abort
from docker import Client
from docker.utils import kwargs_from_env
from ConfigParser import SafeConfigParser
from pymongo import MongoClient
from flask.ext.pymongo import PyMongo
import requests
from git import Repo, Git
from pprint import pprint

app = Flask(__name__)
api = Api(app)
cli = Client(**kwargs_from_env(assert_hostname=False))

app.config['MONGO_DBNAME'] = 'docker_build_service'
mongo = PyMongo(app)

git_base = '/var/tmp/'

class Home(Resource):
	def get(self):
		return ('Welcome!')

class ListDockerImages(Resource):
	def get(self):
		images = cli.images()
 		return {'docker_images': images}

class RegisteredApps(Resource):

	def get(self):
		app_list = json.loads(json_util.dumps(mongo.db.docker_apps.find({},{'_id': 0})))
		return {'apps': app_list}

	def post(self):
		parser = reqparse.RequestParser()
		parser.add_argument('app_name', required=True)
		parser.add_argument('git_url', required=True)
		parser.add_argument('git_ref', required=True)
		args = parser.parse_args()
        
		if mongo.db.docker_apps.find_one({'app_name':args['app_name']}):
			abort(500, message='App Already Exists')

		r = requests.get(args['git_url'])

		if r.status_code == int('200'):
			git_clone_dir = git_base+args['app_name']

			try:
				if os.path.isdir(git_clone_dir):
					shutil.rmtree(git_clone_dir, ignore_errors=True)
				Repo.clone_from(args['git_url'], git_clone_dir, branch='master')
				g = Git(git_clone_dir)
				g.checkout(args['git_ref'])
			except:
				abort(500, message='Failed To Clone Git Repo')

			try:
				repo = Repo(git_clone_dir)
				sha = repo.head.object.hexsha
				short_sha = repo.git.rev_parse(sha, short=7)
				response = [line for line in cli.build(path=git_clone_dir, tag=args['app_name']+'/'+short_sha+'/'+args['git_ref'])]
				pprint(response) # Need to add to mongodb log database
			except:
				abort(500, message='Failed To Build Docker Container')

			try:
				mongo.db.docker_apps.create_index('app_name',unique=True)
				mongo_insert = mongo.db.docker_apps.insert({'app_name':args['app_name'],'git_url':args['git_url']},{'_id': 0})
			except:
				abort(500, message='Database Updage Failed')

		else:
			abort(500, message="Invalid GIT URL")
		return args
		

api.add_resource(Home,'/')
api.add_resource(ListDockerImages, '/images')
api.add_resource(RegisteredApps, '/apps')


if __name__ == '__main__':
    app.run(debug=True)
