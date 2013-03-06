import os
import logging
import random
import Cookie

from google.appengine.api import memcache
from google.appengine.api import xmpp
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import util

from twilio import twiml

#
# (0) Callers start a test by texting 'start' to the app number
# (1) System greets new callers asks what type of quiz and starts the quiz
# (2) System caries on conversation with caller via SMS with ten problems
# (3) At end of test, system stores results and reports to caller on score
#


# Data model to store callers
class User(db.Model):
  phone = db.StringProperty()
  date  = db.DateTimeProperty(auto_now_add=True)
##

class ProblemLog(db.Model):
  phone = db.StringProperty(indexed=True)
  date  = db.DateTimeProperty(auto_now_add=True)
  
  problem_type = db.StringProperty()
  num1 = db.IntegerProperty()
  num2 = db.IntegerProperty()
  answer = db.IntegerProperty()
  
  correct = db.BooleanProperty()
## end 

class TestHandler(webapp.RequestHandler):
    def get(self):
        num1 = random.randint(0,10)
        num2 = random.randint(0,10)
        cookie_question = '%s-%s-m' % (num1,num2)
        cookie_counter = 1
        question = '%s x %s' % (str(num1), str(num2))
        self.response.headers.add_header("Set-Cookie", createCookie('question',cookie_question))
        self.response.headers.add_header("Set-Cookie", createCookie('counter',cookie_counter))
        self.response.out.write(question)
        
class XmppHandler(webapp.RequestHandler):
    def get(self):
        self.post()
        
    def post(self):
      message = xmpp.Message(self.request.POST)
      total_questions = 10
      
      # who called? and what did they say?
      if message.sender.find('@'):
          phone = message.sender.split('/')[0]
      else:
          phone = message.sender.get('from')
      msg = message.body.lower()

      # create a user instance if we need to
      create_user(phone)
      
      #self.response.headers['Content-Type'] = "text/xml; charset=utf-8"
      
      # take a look at the request and see if it is valid
      # if it is, process the request
      
      if msg.lower() == 'start':
          
          memcache.set(phone,0)
          
          num1 = random.randint(0,10)
          num2 = random.randint(0,10)
          cookie_counter = 1
          cookie_question = '%s-%s-m-%s' % (num1,num2,cookie_counter)
          question = "welcome! i'll send %s questions. just reply with your answer. here's the first - %s x %s" % (str(total_questions),str(num1), str(num2))
          
          logging.debug('cookie_question %s' % cookie_question)
          memcache.set('question',cookie_question)
          message.reply(question)

      elif msg.isdigit():
          
          # validate answer message
          cookie_question = memcache.get('question')
          if cookie_question is not None:
             
              # current state is stored in cookies
              cookie_counter = int(cookie_question.split('-')[3])

              # check answer
              answer = computeAnswer(cookie_question, int(msg))
              if answer == int(msg):
                  correct = True
                  memcache.incr(phone)
              else:
                  correct = False

              encourage = pickFeedback(correct, answer)     
              
              # store the problem in the datastore
              createLog(phone,cookie_question,msg,correct)
              
              # are we done yet?
              if cookie_counter == total_questions:
                  # compute results
                  message.reply('%s all done! you got %s out of %s correct.' % (encourage, memcache.get(phone),total_questions))
              else:
                  # provide feedback and move to the next problem
                  cookie_counter += 1
                  cookie_question = createProblem(cookie_counter)
                  question = createQuestionString(cookie_question)
                  memcache.set('question',cookie_question)
                  message.reply(encourage + question)
                                    
          else:
              logging.error('missing cookie')
              logging.debug(self.request.cookies)
              message.reply('something broke inside the app! i need to stop. :(')
              
      else:
        response = 'Yah. Nice try. I need numbers dude'
        message.reply(response)
        
      return
      

## end XmppHandler

class MainHandler(webapp.RequestHandler):
        
    def post(self):

      total_questions = 10
      
      # who called? and what did they say?
      phone = self.request.get("From")
      msg = self.request.get("Body")

      # create a user instance if we need to
      create_user(phone)
      
      #self.response.headers['Content-Type'] = "text/xml; charset=utf-8"
      
      # take a look at the request and see if it is valid
      # if it is, process the request
      
      if msg.lower() == 'start':
          
          memcache.set(phone,0)
          
          num1 = random.randint(0,10)
          num2 = random.randint(0,10)
          cookie_counter = 1
          cookie_question = '%s-%s-m-%s' % (num1,num2,cookie_counter)
          question = "welcome! i'll send %s questions. just reply with your answer. here's the first - %s x %s" % (str(total_questions),str(num1), str(num2))
          
          logging.debug('cookie_question %s' % cookie_question)
          self.response.headers.add_header("Set-Cookie", createCookie('question',cookie_question))
          self.response.out.write(smsResponse(question))

      elif msg.isdigit():
          
          # validate answer message
          if 'question' in self.request.cookies:
             
              # current state is stored in cookies
              cookie_question = self.request.cookies['question']
              cookie_counter = int(cookie_question.split('-')[3])

              # check answer
              answer = computeAnswer(cookie_question, int(msg))
              if answer == int(msg):
                  correct = True
                  memcache.incr(phone)
              else:
                  correct = False

              encourage = pickFeedback(correct, answer)     
              
              # store the problem in the datastore
              createLog(phone,cookie_question,msg,correct)
              
              # are we done yet?
              if cookie_counter == total_questions:
                  # compute results
                  self.response.out.write(smsResponse('%s all done! you got %s out of %s correct.' % (encourage, memcache.get(phone),total_questions)))
              else:
                  # provide feedback and move to the next problem
                  cookie_counter += 1
                  cookie_question = createProblem(cookie_counter)
                  question = createQuestionString(cookie_question)
                  self.response.headers.add_header("Set-Cookie", createCookie('question',cookie_question))
                  self.response.out.write(smsResponse(encourage + question))
                                    
          else:
              logging.error('missing cookie')
              logging.debug(self.request.cookies)
              self.response.out.write(smsResponse('something broke inside the app! i need to stop. :('))
              
      else:
        response = 'Yah. Nice try. I need numbers dude'
        self.response.out.write(smsResponse(response))
        
      return
      
## end XmppHandler

def createProblem(counter):
    
    if random.randint(0,10) < 5:
        # create multiplication problem
        num1 = random.randint(5,9)
        num2 = random.randint(4,10)
        return '%s-%s-m-%s' % (num1,num2,counter)
    else:
        # create division problem
        num1 = random.randint(5,9)
        num2 = random.randint(5,10)
        return '%s-%s-d-%s' % (num1*num2,num1,counter)
        
# end

def createQuestionString(question):
    parts = question.split('-')
    if parts[2] == 'm':
        return '%s x %s' % (parts[0],parts[1])
    else:
        return '%s / %s' % (parts[0],parts[1])
# end

def pickFeedback(correct, answer):
    if correct:
        return 'Yes!  '
    else:
        return ':( The answer was %s   ' % str(answer)
# end

def computeAnswer(question, answer):
    parts = question.split('-')
    if parts[2] == 'm':
        return int(parts[0]) * int(parts[1])
    else:
        return int(parts[0]) / int(parts[1])
# end

def smsResponse(msg):
    r = twiml.Response()
    r.append(twiml.Sms(msg))
    return r
    #return '<Response><Sms>%s</Sms></Response>' % msg

def create_user(phone):
    user = db.GqlQuery("select * from User where phone = :1", phone).get()
    if user is None:
        logging.debug('adding new user %s to the system' % phone)
        user = User()
        user.phone = phone
        user.put()

def createLog(phone,question,answer,correct):
    log = ProblemLog()
    log.phone = phone
    
    parts = question.split('-')
    log.num1 = int(parts[0])
    log.num2 = int(parts[1])
    log.answer = int(answer)
    log.problem_type = 'multiplication' if parts[2] == 'm' else 'division' 
    log.correct = correct
    log.put()

def createCookie(cookieName, cookieVal):
    cookie = Cookie.SimpleCookie()
    cookie[cookieName] = cookieVal
    return cookie.output(header='')
##


def main():
    logging.getLogger().setLevel(logging.DEBUG)
    application = webapp.WSGIApplication([('/sms', MainHandler),
                                          ('/_ah/xmpp/message/chat/', XmppHandler),
                                          ('/test', TestHandler)
                                         ],
                                         debug=True)
    util.run_wsgi_app(application)


if __name__ == '__main__':
    main()
