from zope.interface.declarations import implements
from gorynych.info.domain.person import PersonFactory, IPersonRepository
from gorynych.common.exceptions import NoAggregate

SQL_SELECT_PERSON = "SELECT \
PERSON_ID \
, LASTNAME \
, FIRSTNAME \
, COUNTRY \
, EMAIL \
, REGDATE \
FROM PERSON WHERE EMAIL = %s\
"
SQL_INSERT_PERSON = "INSERT INTO PERSON(\
FIRSTNAME \
, LASTNAME \
, REGDATE \
, EMAIL \
, COUNTRY \
)VALUES(%s, %s, %s, %s, %s) \
RETURNING PERSON_ID, EMAIL"

SQL_UPDATE_PERSON = "UPDATE PERSON SET \
FIRSTNAME = %s\
, LASTNAME = %s\
, REGDATE = %s\
, COUNTRY = %s \
WHERE EMAIL = %s\
"


class PGSQLPersonRepository(object):
    implements(IPersonRepository)

    def __init__(self, pool):
        self.pool = pool

    def _process_select_result(self, data):
        if len(data) == 1:
            data_row = data[0]
            if data_row is not None:
                regdate = data_row[5]
                factory = PersonFactory()
                result = factory.create_person(
                    data_row[1],
                    data_row[2],
                    data_row[3],
                    data_row[4],
                    regdate.year,
                    regdate.month,
                    regdate.day)
                return result
        raise NoAggregate("Person")

    def _process_insert_result(self, data, value):
        if data is not None and value is not None:
            inserted_id = data[0][0]
            value.id = inserted_id
            return value
        return None

    def _params(self, value=None, with_id=False):
        if value is None:
            return ()
        if with_id:
            return (value.name().surname(), value.name().name(), value.regdate,
                    value.country().code(), value.email)
        return (value.name().surname(), value.name().name(), value.regdate,
                value.email, value.country().code())

    def get_by_id(self, person_id):
        # searching in record cache
        # actually, as ID we use unique email address
        # create_person(name, surname, country, email, year, month, day)
        if person_id in self.record_cache:
            return self.record_cache[person_id]
        # if record is not in cache - then load record from DB
        if self.connection is not None:
            cursor = self.connection.cursor()
            cursor.execute(SQL_SELECT_PERSON, (person_id,))
            data_row = cursor.fetchone()
            if data_row is not None:
                # returned_person_id = data_row[0]
                person_firstname = data_row[1]
                person_lastname = data_row[2]
                person_regdate = data_row[3]
                person_email = data_row[4]
                person_country = data_row[5]
                # copy to cache
                # create person object from data and return result
                factory = PersonFactory()
                result = factory.create_person(
                    person_lastname, 
                    person_firstname, 
                    person_country, 
                    person_email,
                    person_regdate.year, 
                    person_regdate.month, 
                    person_regdate.day)
                self.record_cache[person_email] = result
                return result
        raise NoAggregate("Person")

    def save(self, value):
        try:
            if self.connection is not None:
                cursor = self.connection.cursor()
                if value.id is None:
                    cursor.execute(SQL_INSERT_PERSON,
                                   self._params(value))
                    data_row = cursor.fetchone()
                    if data_row is not None:
                        value.id = data_row[1]
                else:
                    cursor.execute(SQL_UPDATE_PERSON,
                                   self._params(value, True))
            self.record_cache[value.id] = value
            return value
        except Exception:
            return None

