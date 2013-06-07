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
  HQ_LON REAL
);

CREATE TABLE PARTICIPANT(
  ID BIGINT REFERENCES CONTEST(ID),
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

-- Insert Contest
INSERT INTO CONTEST(
  TITLE, START_TIME, END_TIME, TIMEZONE, PLACE, COUNTRY, HQ_LAT, HQ_LON, CONTEST_ID)
  VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
RETURNING ID;

-- Select Contest
SELECT * FROM CONTEST WHERE CONTEST_ID = %s;

-- Insert participant
INSERT INTO PARTICIPANT(
  ID, PARTICIPANT_ID, ROLE, GLIDER, CONTEST_NUMBER, DESCRIPTION, TYPE)
VALUES (
  (SELECT id FROM CONTEST WHERE CONTEST.CONTEST_ID=%s),
  %s, %s, %s, %s, %s, %s);

-- Select participants
SELECT * FROM PARTICIPANT WHERE ID=%s;


-- Update contest
UPDATE CONTEST SET (
  TITLE, START_TIME, END_TIME, TIMEZONE, PLACE, COUNTRY, HQ_LAT, HQ_LON)
= (%s, %s, %s, %s, %s, %s, %s, %s)
WHERE CONTEST_ID=%s;