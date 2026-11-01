import type { StudentService } from "../studentService";

// A carry-assistant example using the same interaction API as My service.
export const carryService: StudentService = {
  title: "Carry helper",
  async run(service) {
    await service.waitForPerson();
    await service.approachPerson();
    if (!await service.ask("Would you like help carrying your belongings?")) {
      service.say("No problem. Ask me again when you need help.");
      return;
    }
    await service.confirm("Place your belongings on the rover.", "Items are loaded");
    service.say("I will follow you. Press We have arrived when you reach your destination.");
    await service.followPerson();
    service.say("We have arrived. Please take your belongings.");
  }
};
