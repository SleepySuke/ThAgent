package com.suke.ai.controller;

import jakarta.annotation.Resource;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

/**
 * @author 自然醒
 * @version 1.0
 */
@RestController
public class StreamOutputController {
    @Resource(name = "deepseek")
    private ChatModel deepseekModel;
    @Resource(name = "qwen")
    private ChatModel qwenModel;

    @GetMapping("/stream/chatflux1")
    public Flux<String> chatFlux1(@RequestParam(name = "msg",defaultValue = "请问你是谁")String msg){
        return deepseekModel.stream(msg);
    }
    @GetMapping("/stream/chatflux2")
    public Flux<String> chatFlux2(@RequestParam(name = "msg",defaultValue = "请问你是谁")String msg){
        return qwenModel.stream(msg);
    }

    @Resource(name = "deepseekChatClient")
    private ChatClient deepseekClient;
    @Resource(name = "qwenChatClient")
    private ChatClient qwenClient;
    @GetMapping("/stream/chatflux3")
    public Flux<String> chatFlux3(@RequestParam(name = "msg",defaultValue = "请问你是谁")String msg){
        return deepseekClient.prompt().user(msg).stream().content();
    }

    @GetMapping("/stream/chatflux4")
    public Flux<String> chatFlux4(@RequestParam(name = "msg",defaultValue = "请问你是谁")String msg){
        return qwenClient.prompt(msg).stream().content();
    }


}
