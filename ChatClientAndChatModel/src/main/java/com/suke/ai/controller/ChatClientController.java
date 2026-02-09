package com.suke.ai.controller;

import com.suke.ai.advisor.SimpleMessageAdvisor;
import com.suke.ai.repository.DBChatMemoryRepository;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.client.advisor.MessageChatMemoryAdvisor;
import org.springframework.ai.chat.memory.InMemoryChatMemoryRepository;
import org.springframework.ai.chat.memory.MessageWindowChatMemory;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.tool.ToolCallbackProvider;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * @author 自然醒
 * @version 1.0
 */
@RestController
@Slf4j
public class ChatClientController {
    private final ChatClient chatClient;

    public ChatClientController(ChatModel chatModel, ToolCallbackProvider toolCallbackProvider, DBChatMemoryRepository dbChatMemoryRepository) {
        MessageWindowChatMemory memory = MessageWindowChatMemory.builder().maxMessages(100).chatMemoryRepository(dbChatMemoryRepository).build();
        MessageChatMemoryAdvisor memoryAdvisor = MessageChatMemoryAdvisor.builder(memory).build();
        this.chatClient = ChatClient.builder(chatModel).defaultToolCallbacks(toolCallbackProvider).defaultAdvisors(memoryAdvisor).build();
    }

    @GetMapping("/chatclient/dochat")
    public String doChat(@RequestParam(name = "msg",defaultValue = "2加12等于几")String msg){
        String content = chatClient.prompt().user(msg).call().content();
        return content;
    }

    @GetMapping("/advisor")
    public String doAdvisor(@RequestParam(name = "msg")String msg){
        String content = chatClient.prompt().user(msg).advisors(new SimpleMessageAdvisor()).call().content();
        return content;
    }

    @GetMapping("/advisor01")
    public String doAdvisor01(@RequestParam(name = "msg")String msg,@RequestParam(name = "id")String id){
        String content = chatClient.prompt().user(msg).advisors(advisorSpec -> advisorSpec.param("id",id)).call().content();
        return content;
    }

    @GetMapping("/memory")
    public String doMemory(@RequestParam(name = "msg")String msg,@RequestParam(name = "id")String id){
        String content = chatClient.prompt().user(msg).advisors(advisorSpec -> advisorSpec.param("id",id)).call().content();
        return content;
    }

}
