// ESM
import { faker } from '@faker-js/faker';

function createRandomUser() {
  return {
    email: faker.internet.email(),
    password: faker.internet.password(),
    first_name: faker.name.firstName(),
    profile_picture: faker.image.avatar(),
  };
}

for (let index = 0; index < 50; index++) {
  console.log(createRandomUser(), ',');
}
