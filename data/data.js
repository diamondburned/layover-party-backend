// ESM
import { faker } from '@faker-js/faker';
import { iata } from './iata.js';

function createRandomUser() {
  return {
    email: faker.internet.email(),
    password: faker.internet.password(),
    first_name: faker.name.firstName(),
    profile_picture: faker.image.avatar(),
  };
}

function addDays(date, days) {
  date.setDate(date.getDate() + days);
  return date;
}

for (let index = 0; index < 50; index++) {
  console.log(JSON.stringify(createRandomUser()), ',');
}

function createLayover() {
  const depart = faker.date.future();
  return {
    iata_code: iata[Math.floor(Math.random() * iata.length)].code,
    depart: depart,
    arrive: addDays(depart, 5),
  };
}

for (let index = 0; index < 500; index++) {
  console.log(JSON.stringify(createLayover()), ',');
}