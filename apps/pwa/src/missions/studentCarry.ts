import type { StudentService } from "../service/studentService";

// Edit only this file for the workshop. Save, then rerun at /app?service=student.
export const studentCarry: StudentService = {
  title: "My carry service",
  async run(service) {
    await service.waitForPerson();
    await service.approachPerson();
    if (!await service.ask("Would you like help carrying your belongings?")) {
      service.say("No problem. Ask me again when you need help.");
      return;
    }
    await service.confirm("Place your belongings on the rover.", "Items are loaded");
    service.say("I will follow you. Press We have arrived when you reach your destination.");
    await service.followPerson({
      message: "Press We have arrived when you reach your destination",
      buttonLabel: "We have arrived"
    });
    service.say("We have arrived. Please take your belongings.");
  }
};
