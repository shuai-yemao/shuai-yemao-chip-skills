/**
 * Embedded Peripherals Plugin
 * 常用外设模块技能包
 */

const path = require('path');
const fs = require('fs');

class EmbeddedPeripheralsPlugin {
  constructor() {
    this.name = 'embedded-peripherals';
    this.version = '1.0.0';
    this.skills = {};
    this.config = {};
  }

  async onInstall(context) {
    console.log(`[${this.name}] 插件安装中...`);
    await this.loadSkills(context.skillsDir);
    this.config = { ...this.config, ...context.config };
    console.log(`[${this.name}] 插件安装完成`);
  }

  async onUninstall(context) {
    console.log(`[${this.name}] 插件卸载中...`);
    this.skills = {};
    this.config = {};
    console.log(`[${this.name}] 插件卸载完成`);
  }

  async loadSkills(skillsDir) {
    const skillDirs = [
      'adc-module', 'timer-module', 'watchdog-module', 'peripheral-driver',
      'dma-module', 'usb-module', 'motor-control', 'flash-module', 'sram-module'
    ];

    for (const skillName of skillDirs) {
      const skillPath = path.join(skillsDir, skillName);
      if (fs.existsSync(skillPath)) {
        this.skills[skillName] = {
          name: skillName,
          path: skillPath,
          loaded: true
        };
      }
    }
  }

  getSkill(name) {
    return this.skills[name] || null;
  }

  listSkills() {
    return Object.keys(this.skills);
  }

  getConfig() {
    return { ...this.config };
  }
}

module.exports = new EmbeddedPeripheralsPlugin();
