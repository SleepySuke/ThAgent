package com.suke.ai.test;

import com.suke.ai.mapper.ContentMapper;
import com.suke.ai.pojo.Content;
import com.suke.ai.repository.DBChatMemoryRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.ai.chat.messages.Message;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDateTime;
import java.util.List;

/**
 * @author 自然醒
 * @version 1.0
 * @date 2026-02-09 16:11
 * @description 持久化基准测试接口
 */
@RestController
@RequiredArgsConstructor
public class TestController {
    @Autowired
    private ContentMapper contentMapper;

    private final ChatServiceTest chatService;

    /**
     * 测试数据库连接和插入
     */
    @GetMapping("/test/insert")
    public String testInsert(@RequestParam(name = "conversationId", defaultValue = "test_conv_001") String conversationId) {
        String s = chatService.testInsert(conversationId);
        System.out.println(s);
        return s;
    }

    /**
     * 测试查询对话ID列表
     */
    @GetMapping("/test/conversations")
    public Object testFindConversations() {
        try {
            return contentMapper.findConversationIds();
        } catch (Exception e) {
            return "查询失败: " + e.getMessage();
        }
    }

    /**
     * 测试根据对话ID查询
     */
    @GetMapping("/test/findByConversation")
    public Object testFindByConversation(@RequestParam(name = "conversationId") String conversationId) {
        try {
            return contentMapper.findByConversationId(conversationId);
        } catch (Exception e) {
            return "查询失败: " + e.getMessage();
        }
    }

    /**
     * 测试删除
     */
    @GetMapping("/test/delete")
    public String testDelete(@RequestParam(name = "conversationId") String conversationId) {
        try {
            contentMapper.deleteByConversationId(conversationId);
            return "删除成功: " + conversationId;
        } catch (Exception e) {
            return "删除失败: " + e.getMessage();
        }
    }
}
