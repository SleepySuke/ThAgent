package com.suke.ai.pojo;

import lombok.Data;

import java.time.LocalDateTime;

/**
 * @author 自然醒
 * @version 1.0
 * @date 2026-02-09 14:46
 * @description 对话信息实体类
 */
@Data
public class Content {
    //主键ID
    private Integer id;
    //对话信息id 为其建立一个唯一索引方便查找
    private String conversationId;
    //用户的消息
    private String userContent;
    //AI回复的消息
    private String assistantContent;
    //todo 实际的话会有一个用户id，应该是三张表将对话信息存储 这里暂且不实现
    private Integer userId;
    //第一次存储的时间戳
    private LocalDateTime createTime;
    //新对话的更新时间
    private LocalDateTime updateTime;
}
