package com.suke.ai.controller;

import jakarta.annotation.Resource;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * @author 自然醒
 * @version 1.0
 */
@RestController
public class ChatClientControllerV2 {
    @Resource
    private ChatModel chatModel;
    @Resource
    private ChatClient chatClient;

    @GetMapping("/chatclientV2/dochat")
    public String doChatWithChatClient(@RequestParam(name = "msg",defaultValue = "请问你是谁")String msg){
        String content = chatClient.prompt().user(msg).call().content();
        System.out.println("ChatClient回显:"+ content);
        return content;
    }

    @GetMapping("/chatmodelV2/dochat")
    public String doChatWithChatModel(@RequestParam(name = "msg",defaultValue = "请问你是谁")String msg){
        String call = chatModel.call(msg);
        System.out.println("ChatModel回显:"+ call);
        return call;
    }
}
