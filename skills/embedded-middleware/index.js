/**
 * Embedded Middleware Plugin
 * 嵌入式中间件技能包
 */

const path = require('path');
const fs = require('fs');

class EmbeddedMiddlewarePlugin {
  constructor() {
    this.name = 'embedded-middleware';
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
      'fatfs-module', 'aes-module', 'rsa-module', 'crc-module',
      'ymodem-module', 'lora-module', 'lvgl-module',
      'dsp-module', 'fft-module', 'sfud-module', 'elog-module'
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

module.exports = new EmbeddedMiddlewarePlugin();
