package com.suke.ai.test;

import com.suke.ai.mapper.ContentMapper;
import com.suke.ai.pojo.Content;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.messages.Message;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

/**
 * @author 自然醒
 * @version 1.0
 * @date 2026-02-09 16:59
 * @description 模拟测试插入
 */
@Service
@Slf4j
public class ChatServiceTest {
    @Autowired
    private ContentMapper contentMapper;

    @Transactional
    public String testInsert(String conversationId){
        Content content = new Content();
        content.setConversationId(conversationId);
        content.setUserContent("测试用户消息");
        content.setAssistantContent("测试AI回复");
        content.setUserId(1);
        content.setCreateTime(LocalDateTime.now());
        content.setUpdateTime(LocalDateTime.now());

        try {
            contentMapper.insert(content);
            return "插入成功，ID: " + content.getId();
        } catch (Exception e) {
            return "插入失败: " + e.getMessage();
        }
    }
}
