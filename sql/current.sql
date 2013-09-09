﻿-- DB schema for gorynych.
-- Here I assume that database has been prepared already.
DROP SCHEMA PUBLIC CASCADE ;
CREATE SCHEMA PUBLIC;

-- Aggregate Person ---------------------------------------

CREATE TABLE PERSON(
  ID BIGSERIAL PRIMARY KEY,
  NAME TEXT NOT NULL,
  SURNAME TEXT NOT NULL,
  REGDATE TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  EMAIL TEXT UNIQUE,
  COUNTRY TEXT,
  PERSON_ID TEXT UNIQUE NOT NULL
);

CREATE TABLE PERSON_DATA(
  ID BIGINT REFERENCES PERSON(ID) ON DELETE CASCADE ,
  DATA_TYPE TEXT NOT NULL ,
  DATA_VALUE TEXT NOT NULL,

  PRIMARY KEY (ID, DATA_TYPE, DATA_VALUE)
);

CREATE UNIQUE INDEX UNIQUE_PHONE
ON PERSON_DATA (ID, DATA_VALUE)
WHERE DATA_TYPE='phone';

-- Aggregate Contest ------------------------------------

CREATE TABLE CONTEST(
  ID BIGSERIAL PRIMARY KEY,
  CONTEST_ID TEXT UNIQUE NOT NULL,
  TITLE TEXT,
  START_TIME INTEGER ,
  END_TIME INTEGER ,
  TIMEZONE TEXT,
  PLACE TEXT,
  COUNTRY TEXT,
  HQ_LAT REAL,
  HQ_LON REAL,

  UNIQUE (TITLE, START_TIME, END_TIME, COUNTRY)
);

CREATE TABLE PARTICIPANT(
  ID BIGINT REFERENCES CONTEST(ID) ON DELETE CASCADE,
  PARTICIPANT_ID TEXT ,
  ROLE TEXT NOT NULL,
  -- for paragliders
  GLIDER TEXT,
  CONTEST_NUMBER TEXT,
  DESCRIPTION TEXT,
  -- person, transport
  TYPE TEXT NOT NULL,

  PRIMARY KEY (ID, PARTICIPANT_ID)
);

CREATE UNIQUE INDEX UNIQUE_CONTEST_NUMBER ON PARTICIPANT (ID, CONTEST_NUMBER) WHERE ROLE='PARAGLIDER';

CREATE TABLE CONTEST_RETRIEVE_ID(
  ID BIGINT REFERENCES CONTEST(ID) ON DELETE CASCADE PRIMARY KEY ,
  RETRIEVE_ID TEXT
);


-- Aggregate Race --------------------------------------

CREATE TABLE RACE_TYPE(
  ID BIGSERIAL PRIMARY KEY,
  -- opendistance, racetogoal, speedrun etc.
  TYPE TEXT UNIQUE NOT NULL
);
INSERT INTO RACE_TYPE(TYPE) VALUES ('racetogoal'), ('speedrun'),
('opendistance');

CREATE TABLE RACE(
  ID BIGSERIAL PRIMARY KEY,
  RACE_ID TEXT UNIQUE NOT NULL,
  TITLE TEXT,
  START_TIME INTEGER NOT NULL,
  END_TIME INTEGER NOT NULL,
  TIMEZONE TEXT NOT NULL ,
  RACE_TYPE BIGINT REFERENCES RACE_TYPE(ID),
  CHECKPOINTS TEXT NOT NULL,
  AUX_FIELDS TEXT,
  START_LIMIT_TIME INTEGER ,
  END_LIMIT_TIME INTEGER
);


CREATE TABLE PARAGLIDER(
  ID BIGINT REFERENCES RACE(ID) ON DELETE CASCADE ,
  PERSON_ID TEXT NOT NULL,
  CONTEST_NUMBER TEXT,
  COUNTRY TEXT NOT NULL ,
  GLIDER TEXT NOT NULL ,
  TRACKER_ID TEXT ,
  NAME TEXT NOT NULL ,
  SURNAME TEXT NOT NULL ,

  PRIMARY KEY (ID, PERSON_ID)
);


CREATE TABLE ORGANIZATOR(
  ID BIGINT REFERENCES RACE(ID) ON DELETE CASCADE ,
  PERSON_ID TEXT NOT NULL,
  DESCRIPTION TEXT ,
  TRACKER_ID TEXT ,

  PRIMARY KEY (ID, PERSON_ID)
);


CREATE TABLE RACE_TRANSPORT(
  ID BIGINT REFERENCES RACE(ID) ON DELETE CASCADE ,
  TRANSPORT_ID TEXT NOT NULL ,
  DESCRIPTION TEXT ,
  TITLE TEXT ,
  TRACKER_ID TEXT NOT NULL ,
  TYPE TEXT NOT NULL ,

  PRIMARY KEY (ID, TRANSPORT_ID)
);

-- Event Store ----------------------------------------
CREATE TABLE IF NOT EXISTS events
(
  EVENT_ID bigserial PRIMARY KEY,
  EVENT_NAME TEXT NOT NULL,
  AGGREGATE_ID TEXT NOT NULL,
  AGGREGATE_TYPE TEXT NOT NULL,
  EVENT_PAYLOAD BYTEA NOT NULL,
  OCCURED_ON TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS dispatch (
  EVENT_ID bigint REFERENCES events(EVENT_ID) ON DELETE CASCADE,
  TAKEN BOOLEAN DEFAULT FALSE ,
  TIME TIMESTAMP DEFAULT NOW(),

  PRIMARY KEY (EVENT_ID)
);

CREATE OR REPLACE FUNCTION add_to_dispatch() RETURNS TRIGGER AS $$
        BEGIN
          INSERT INTO dispatch (EVENT_ID) VALUES (NEW.EVENT_ID);
          RETURN NEW;
        END;
    $$ LANGUAGE plpgsql;

CREATE TRIGGER to_dispatch
AFTER INSERT ON events
FOR EACH ROW EXECUTE PROCEDURE add_to_dispatch();


-- Aggregate Track -------------------------------------

CREATE TABLE TRACK_TYPE(
  ID SERIAL PRIMARY KEY,
  NAME TEXT NOT NULL UNIQUE
);

insert into track_type (name) values('competition_aftertask');

CREATE TABLE TRACK(
	ID SERIAL PRIMARY KEY,
	START_TIME INTEGER ,
	END_TIME INTEGER ,
	TRACK_ID TEXT UNIQUE NOT NULL,
	TRACK_TYPE INT REFERENCES TRACK_TYPE(ID) ON DELETE CASCADE
);

CREATE TABLE TRACK_DATA(
	ID INT REFERENCES TRACK(ID) ON DELETE CASCADE ,
	TIMESTAMP INTEGER,
	LAT DOUBLE PRECISION ,
	LON DOUBLE PRECISION ,
	ALT SMALLINT ,
	G_SPEED REAL,
	V_SPEED REAL,
	DISTANCE INTEGER ,

  PRIMARY KEY (TIMESTAMP, ID)
);

CREATE INDEX track_data_timestamp_idx
  ON track_data
  USING btree (timestamp);

CREATE TABLE TRACK_SNAPSHOT(
  ID INT REFERENCES TRACK(ID) ON DELETE CASCADE ,
  TIMESTAMP INTEGER ,
  SNAPSHOT TEXT NOT NULL,

  PRIMARY KEY (ID, TIMESTAMP)
);

CREATE TABLE TRACKS_GROUP(
  GROUP_ID TEXT ,
  TRACK_ID INT REFERENCES TRACK(ID) ON DELETE CASCADE ,
  TRACK_LABEL TEXT,

  PRIMARY KEY (GROUP_ID, TRACK_ID)
);

-- Aggregate Tracker -------------------------

CREATE TABLE DEVICE_TYPE(
  ID SERIAL PRIMARY KEY,
  NAME TEXT
);

INSERT INTO DEVICE_TYPE (NAME) VALUES ('tr203');

CREATE TABLE TRACKER(
  ID BIGSERIAL PRIMARY KEY,
  DEVICE_ID TEXT NOT NULL,
  DEVICE_TYPE INT REFERENCES DEVICE_TYPE(ID) ON DELETE RESTRICT,
  TRACKER_ID TEXT UNIQUE NOT NULL,
  NAME TEXT,

  UNIQUE (DEVICE_ID, DEVICE_TYPE)
);


CREATE TABLE TRACKER_ASSIGNEES(
  ID BIGINT REFERENCES TRACKER(ID) ON DELETE CASCADE,
  ASSIGNEE_ID TEXT NOT NULL ,
  ASSIGNED_FOR TEXT,

  PRIMARY KEY(ID, ASSIGNED_FOR, ASSIGNEE_ID)
);

CREATE TABLE TRACKER_LAST_POINT(
  ID BIGINT REFERENCES TRACKER(ID) ON DELETE CASCADE PRIMARY KEY ,
  LAT REAL ,
  LON REAL ,
  ALT SMALLINT ,
  TIMESTAMP INTEGER,
  BATTERY SMALLINT,
  SPEED REAL
);


CREATE OR REPLACE FUNCTION add_to_last_point() RETURNS TRIGGER AS $$
        BEGIN
          INSERT INTO tracker_last_point (ID) VALUES (NEW.ID);
          RETURN NEW;
        END;
    $$ LANGUAGE plpgsql;

CREATE TRIGGER to_last_point
    AFTER INSERT ON tracker
    FOR EACH ROW EXECUTE PROCEDURE add_to_last_point();


-- Chat -------------------------------------
CREATE TABLE CHATROOMS (
  ID SERIAL PRIMARY KEY ,
  CHATROOM_NAME TEXT NOT NULL UNIQUE
);

CREATE TABLE MESSAGES(
  ID BIGSERIAL PRIMARY KEY ,
  "FROM" TEXT NOT NULL ,
  SENDER TEXT NOT NULL ,
  "TO" TEXT ,
  BODY BYTEA NOT NULL ,
  TIMESTAMP INTEGER,
  CHATROOM_ID INT REFERENCES CHATROOMS (ID) NOT NULL
);

-- Aggregate Transport -----------------------------------------
CREATE TABLE TRANSPORT_TYPE(
  ID SERIAL PRIMARY KEY ,
  TRANSPORT_TYPE TEXT UNIQUE NOT NULL
);

INSERT INTO TRANSPORT_TYPE(TRANSPORT_TYPE) VALUES ('bus'), ('car'),
('motorcycle'), ('helicopter');

CREATE TABLE TRANSPORT(
  ID BIGSERIAL PRIMARY KEY ,
  TRANSPORT_ID TEXT UNIQUE NOT NULL ,
  TITLE TEXT NOT NULL ,
  TYPE INT REFERENCES TRANSPORT_TYPE(ID) NOT NULL ,
  DESCRIPTION TEXT
);