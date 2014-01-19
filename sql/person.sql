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

  PRIMARY KEY (ID, DATA_TYPE, DATA_VALUE),
  UNIQUE(ID, DATA_TYPE)
);

CREATE UNIQUE INDEX UNIQUE_PHONE
ON PERSON_DATA (ID, DATA_VALUE)
WHERE DATA_TYPE='phone';

-- Insert Person
INSERT INTO PERSON(NAME, SURNAME, REGDATE, COUNTRY, EMAIL, PERSON_ID)
    VALUES (%s, %s, %s, %s, %s, %s)
    RETURNING ID;

-- Select Person
SELECT
  NAME, SURNAME, COUNTRY, EMAIL, REGDATE, PERSON_ID, ID
FROM
  PERSON
WHERE PERSON_ID=%s;

-- Select all_person
SELECT
  PERSON_ID, NAME, SURNAME, COUNTRY, EMAIL, REGDATE, PERSON_ID, ID
FROM PERSON;

-- Update Person
UPDATE PERSON SET
  NAME=%s,
  SURNAME=%s,
  REGDATE=%s,
  COUNTRY=%s,
  EMAIL=%s
WHERE PERSON_ID = %s;

-- select by_email
SELECT PERSON_ID FROM PERSON WHERE EMAIL=%s;

-- Insert person_data
INSERT INTO PERSON_DATA(ID, DATA_TYPE, DATA_VALUE)
    VALUES (%s, %s, %s);

-- Update person_data
UPDATE PERSON_DATA SET
  DATA_VALUE=%s
WHERE
  ID=%s AND
  DATA_TYPE=%s;

-- Select current_contests
SELECT
    C.contest_id
FROM
    CONTEST C,
    PARTICIPANT P
WHERE
    C.id=P.id AND
    P.participant_id=%s AND
    %s BETWEEN C.start_time and C.end_time;


-- Select next_contest
WITH
    future_contests
AS
    (SELECT
        C.contest_id,
        C.start_time
    FROM
        CONTEST C,
        PARTICIPANT P
    WHERE
        C.id=P.id AND
        P.participant_id=%s AND
        C.start_time > %s)
SELECT
    contest_id
FROM
    future_contests
WHERE
    start_time = (SELECT MIN(start_time) from future_contests);
