from .db import db
from werkzeug.security import check_password_hash
from flask_login import UserMixin
from datetime import datetime

class User(UserMixin, db.Model):
  id = db.Column(db.Integer, primary_key=True)
  username = db.Column(db.String(80), unique=True, nullable=False)
  realname = db.Column(db.String(80), nullable=False)
  password_hash = db.Column(db.String(250), nullable=False)
  #1 = user (read only), 255 = admin - see functions/rights_required.py
  rights = db.Column(db.Integer, nullable=False, default=1)
  created = db.Column(db.DateTime, default=datetime.now)
  def check_password(self, password):
    return check_password_hash(self.password_hash, password)

class Settings(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  logFile = db.Column(db.String(512), nullable=False)
  sessionKey = db.Column(db.String(64), nullable=False)
  storagePath = db.Column(db.String(512), nullable=False)
  sortBy = db.Column(db.String(16), nullable=False, default="sender")
  recipientHeaders = db.Column(db.String(512), nullable=True, default="To,Cc,X-Original-To,Delivered-To")
  multiDomainMode = db.Column(db.String(16), nullable=True, default="first")
  ignoreDomains = db.Column(db.String(1024), nullable=True, default="")
  deleteFromServer = db.Column(db.String(10), nullable=True, default="false")
  imapTimeout = db.Column(db.String(10), nullable=True, default="60")
  fetchToken = db.Column(db.String(128), nullable=True, default="")
  telegramChat = db.Column(db.String(32), nullable=True, default="")
  telegramToken = db.Column(db.String(128), nullable=True, default="")
  serverHostname = db.Column(db.String(256), nullable=True, default="")

class Mailbox(db.Model):
  #IMAP account the mail is collected from
  id = db.Column(db.Integer, primary_key=True)
  name = db.Column(db.String(128), nullable=False, unique=True)
  host = db.Column(db.String(256), nullable=False)
  port = db.Column(db.Integer, nullable=False, default=993)
  security = db.Column(db.String(10), nullable=False, default="ssl")   #"ssl" | "starttls" | "none"
  username = db.Column(db.String(256), nullable=False)
  password = db.Column(db.String(512), nullable=False)
  folders = db.Column(db.String(1024), nullable=False, default="INBOX") #comma-separated IMAP folders
  enabled = db.Column(db.Boolean(), nullable=False, default=True)
  last_fetch = db.Column(db.DateTime, nullable=True)
  last_status = db.Column(db.String(1024), nullable=True, default="")
  last_count = db.Column(db.Integer, nullable=True, default=0)
  created = db.Column(db.DateTime, default=datetime.now)

class Email(db.Model):
  #one row per (domain, message). In multiDomainMode="all" a message addressed to several domains gets one row
  #(and one .eml copy) in every domain folder.
  __table_args__ = (db.Index("ix_email_domain_received", "domain", "received"),)
  id = db.Column(db.Integer, primary_key=True)
  domain = db.Column(db.String(255), nullable=False)   #indexed by ix_email_domain_received
  mailbox_id = db.Column(db.Integer, nullable=True, index=True)
  mailbox_name = db.Column(db.String(128), nullable=True, default="")
  imap_folder = db.Column(db.String(255), nullable=True, default="")
  message_id = db.Column(db.String(512), nullable=True, default="")
  subject = db.Column(db.String(1000), nullable=True, default="")
  sender = db.Column(db.String(512), nullable=True, default="")
  sender_name = db.Column(db.String(512), nullable=True, default="")
  recipients = db.Column(db.Text, nullable=True)
  date_header = db.Column(db.DateTime, nullable=True)                   #"Date:" header of the message
  received = db.Column(db.DateTime, nullable=False, default=datetime.now) #IMAP INTERNALDATE = when the server got it
  size = db.Column(db.Integer, nullable=True, default=0)
  has_attachments = db.Column(db.Boolean(), nullable=False, default=False)
  file_path = db.Column(db.String(1024), nullable=False)                #relative to Settings.storagePath
  created = db.Column(db.DateTime, default=datetime.now)

class FetchedMessage(db.Model):
  #ledger of every IMAP message that was already downloaded and safely stored - so it's never downloaded twice
  #(when deleteFromServer is off) and is not re-imported after an admin deletes it from the app
  __table_args__ = (db.UniqueConstraint("mailbox_id", "folder", "uidvalidity", "uid", name="uq_fetched_message"),)
  id = db.Column(db.Integer, primary_key=True)
  mailbox_id = db.Column(db.Integer, nullable=False, index=True)
  folder = db.Column(db.String(255), nullable=False)
  uidvalidity = db.Column(db.BigInteger, nullable=False)
  uid = db.Column(db.BigInteger, nullable=False)
  fetched = db.Column(db.DateTime, default=datetime.now)
