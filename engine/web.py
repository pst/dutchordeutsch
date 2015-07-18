#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import json
import yaml
import logging
from functools import wraps
from hashlib import sha1
from random import randint

from jinja2 import Environment as JinjaEnvironment, FileSystemLoader
from webassets import Environment as AssetsEnvironment
from webassets.ext.jinja2 import AssetsExtension
from webassets.filter import register_filter
from webassets_libsass import LibSass
from tornado.options import define, options
import tornado.ioloop
import tornado.web
import tornado.httpserver
import tornado.gen


def force_https(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not args[0].request.protocol == 'https' \
        and not args[0].request.host.startswith('localhost:'):
            args[0].redirect(
                'https://{0}{1}'.format(
                    args[0].request.host, args[0].request.uri),
                permanent=True)
        return f(*args, **kwargs)
    return wrapper


class Application(tornado.web.Application):

    def __init__(self):

        site_path = os.path.join(os.path.abspath('.'), "site", "site.yaml")
        with open(site_path) as f:
            site = yaml.load(f)

        data_path = os.path.join(os.path.abspath('.'), "data")        
        with open(os.path.join(data_path, 'dutch.txt')) as dutch_file:
            dutch_sights = dutch_file.readlines()
        with open(os.path.join(data_path, 'deutsch.txt')) as deutsch_file:
            deutsch_sights = deutsch_file.readlines()

        settings = dict(
            template_path=os.path.join(os.path.abspath('.'), "site", "templates"),
            snippet_path=os.path.join(os.path.abspath('.'), "site", "snippets"),
            static_path=os.path.join(os.path.abspath('.'), "site", "assets"),
            static_url_prefix='/assets/',
            site=site,
            answer_salt=',<1qbl,_a{jJ9',
            sights={'dutch': dutch_sights, 'deutsch': deutsch_sights}
        )

        log = logging.getLogger('tornado.application')

        handlers = [(r"/assets/(.*)",
                        tornado.web.StaticFileHandler,
                        dict(path=settings['static_path'])),
                    (r"/quiz$", QuizHandler),
                    (r"(/[a-z0-9\-_\/]*)$", PageHandler)]

        tornado.web.Application.__init__(self, handlers, **settings)


class EngineMixin(object):

    def stylesheet_tag(self, name):
        return '<link type="text/css" rel="stylesheet" media="screen" href="{0}">'.format(self.static_url(name))

    def javascript_tag(self, name):
        return '<script type="text/javascript" src="{0}"></script>'.format(self.static_url(name))

    def theme_image_url(self, name):
        return '{0}'.format(self.static_url(name))

    def initialize(self):
        loader = FileSystemLoader([
            self.settings['template_path'],
            self.settings['snippet_path']])
        assets_env = AssetsEnvironment(self.settings['static_path'], self.static_url(''))
        register_filter(LibSass)
        self.template_env = JinjaEnvironment(
            loader=loader, extensions=[AssetsExtension])
        self.template_env.assets_environment = assets_env
        self.template_env.filters['stylesheet_tag'] = self.stylesheet_tag
        self.template_env.filters['javascript_tag'] = self.javascript_tag
        self.template_env.filters['theme_image_url'] = self.theme_image_url

        self.template_env.globals = self.get_globals()
        self.site = self.settings['site']

    def get_globals(self):
        globals = {
            'site_env': os.environ.get('SITE_ENV', 'production'),
            'arguments': self.request.arguments,
            'host': self.request.host,
            'remote_ip': self.request.remote_ip,
            'path': self.request.path,
            'uri': self.request.uri,
            'method': self.request.method}
        return globals

    def parse_path(self, slug):
        path = os.path.join(self.settings['page_path'], slug)
        return path

    def get_page(self, slug):
        pages = self.site['pages']
        
        if slug in pages:
            return pages[slug]
        raise tornado.web.HTTPError(404)

    def get_template(self, slug):
        tpl_name = slug
        if slug.endswith('/'):
            tpl_name += 'index.html'
        else:
            tpl_name += '.html'
        return self.template_env.get_template(tpl_name)


class PageHandler(EngineMixin, tornado.web.RequestHandler):

    @force_https
    @tornado.web.removeslash
    def get(self, slug=None):
        page = self.get_page(slug)

        if page['published'] == False:
            raise tornado.web.HTTPError(404)

        template = self.get_template(slug)

        response = template.render(site=self.site, page=page, sights=self.settings['sights'])

        self.write(response)
        self.finish()


class QuizHandler(tornado.web.RequestHandler):

    def hash_answer(self, answer):
        return sha1("{}{}".format(
                self.settings['answer_salt'],
                str(answer))).hexdigest()

    def get_random_sight(self):
        answer = 'dutch'
        if randint(0, 1) == 1:
            answer = 'deutsch'

        pot_sights = self.settings['sights'][answer]

        sight = pot_sights[randint(0, len(pot_sights))]

        return answer, sight

    def get_new_quiz(self):
        answer, sight = self.get_random_sight()
        img_src = 'https://maps.googleapis.com/maps/api/streetview?size=600x300&location={}&heading=151.78&pitch=-0.76'.format(sight)
        quiz = {
            'img_src': img_src,
            'answer': '',
            'hashed_answer': self.hash_answer(answer),
            'result': None}
        return quiz

    def check_answer(self, quiz):
        quiz['result'] = False
        if quiz['hashed_answer'] == self.hash_answer(quiz['answer']):
            quiz['result'] = True
        return quiz

    def prepare(self):
        self.set_header("Content-Type", 'application/json; charset="utf-8"')

    @force_https
    def post(self):
        quiz = self.get_new_quiz()
        self.write(json.dumps(quiz))
        self.finish()

    @force_https
    def put(self):
        quiz = self.check_answer(json.loads(self.request.body))
        self.write(json.dumps(quiz))
        self.finish()
        

define("port", default="5555", help="Port to listen on")


if __name__ == "__main__":
    tornado.options.parse_command_line()
    app = Application()
    server = tornado.httpserver.HTTPServer(app, xheaders=True)
    server.bind(options.port)
    try:
        server.start()
        tornado.ioloop.IOLoop.instance().start()
    except KeyboardInterrupt:
        tornado.ioloop.IOLoop.instance().stop()

