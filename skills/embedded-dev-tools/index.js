/**
 * Embedded Dev Tools Plugin
 * 嵌入式开发工具技能包
 */

const path = require('path');
const fs = require('fs');

class EmbeddedDevToolsPlugin {
  constructor() {
    this.name = 'embedded-dev-tools';
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
      'build-keil', 'build-iar', 'build-cmake', 'build-platformio',
      'flash-jlink', 'flash-keil', 'flash-openocd', 'flash-platformio', 'gang-flash',
      'debug-gdb-openocd', 'serial-monitor', 'segger-rtt-module', 'cmbacktrace-debug', 'embedded-debugger-framework',
      'static-analysis', 'map-analyzer', 'firmware-sign', 'ota-package',
      'pcb-analysis', 'visa-debug'
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

module.exports = new EmbeddedDevToolsPlugin();
