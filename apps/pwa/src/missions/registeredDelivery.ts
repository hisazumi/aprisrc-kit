import type { StudentService } from '../service/studentService.ts';

/** Registered map/place example for the connected simulator host. */
export const registeredDelivery: StudentService = {
  title: '登録地点への配送',
  async run(service) {
    await service.waitForLoaded('荷物を載せてください。');
    service.say('受付へ向かいます。');
    await service.guideTo('desk');
    service.say('受付に到着しました。');
    await service.confirm('荷物を受け取ってください。', '受け取りました');
    service.say('配送を完了しました。');
  },
};
