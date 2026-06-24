/**
 * Embedded Communication Plugin
 * 嵌入式通信协议技能包
 */

const path = require('path');
const fs = require('fs');

class EmbeddedCommunicationPlugin {
  constructor() {
    this.name = 'embedded-communication';
    this.version = '1.0.0';
    this.skills = {};
    this.config = {};
  }

  /**
   * 插件安装
   */
  async onInstall(context) {
    console.log(`[${this.name}] 插件安装中...`);
    
    // 加载 skills
    await this.loadSkills(context.skillsDir);
    
    // 应用配置
    this.config = { ...this.config, ...context.config };
    
    console.log(`[${this.name}] 插件安装完成`);
  }

  /**
   * 插件卸载
   */
  async onUninstall(context) {
    console.log(`[${this.name}] 插件卸载中...`);
    
    // 清理资源
    this.skills = {};
    this.config = {};
    
    console.log(`[${this.name}] 插件卸载完成`);
  }

  /**
   * 加载 skills
   */
  async loadSkills(skillsDir) {
    const skillDirs = [
      'i2c-bus', 'spi-bus', 'uart-module', 'can-debug', 'modbus-debug',
      'ble-module', 'wifi-module', 'lora-module', 'cellular-module', 'gps-module',
      'mqtt-module'
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

  /**
   * 获取 skill
   */
  getSkill(name) {
    return this.skills[name] || null;
  }

  /**
   * 列出所有 skills
   */
  listSkills() {
    return Object.keys(this.skills);
  }

  /**
   * 获取配置
   */
  getConfig() {
    return { ...this.config };
  }
}

// 导出插件
module.exports = new EmbeddedCommunicationPlugin();
