import type { StudentService } from "../studentService";

export const greetingService: StudentService = {
  title: "Person greeting",
  async run(service) {
    await service.greetPerson();
  }
};
